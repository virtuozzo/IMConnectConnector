#******************************************************************************
# Copyright (c) 2020, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
#******************************************************************************

import copy
from datetime import datetime, timedelta
import json
import functools
import logging
from unittest.mock import patch, MagicMock

import pytest

from marshmallow.fields import String, Nested, Integer
from marshmallow.schema import Schema
from connect.models.schemas import (
    UsageFileSchema, FulfillmentSchema, ConversationSchema,
    ConversationMessageSchema, AssetSchema
)

import cloudblue_connector

from cloudblue_connector import (
    ConnectorConfig, process_usage, process_usage_files, process_fulfillment,
    UsageFileAutomation, SubmitUsageFile, SkipRequest, AcceptUsageFile,
    FulfillmentAutomation, UsageAutomation
)

from cloudblue_connector.connector import (
    ActivationTemplateResponse, ActivationTileResponse
)


LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


SUPPORTED_DEFAULTS_KEY_TYPE = (str,)


def gen_fake_by_schema(schema, inners=None, defaults=None):
    """
    Generate fake dict by schema for responses content/data.

    :type schema: Schema
    :type inners: list
    :type defaults: dict
    :rtype: dict
    """
    if inners is None:
        inners = []
    if defaults is None:
        defaults = {}
    elif not isinstance(defaults, dict):
        pytest.fail('Incorrect defaults type. Must be dict.')
    else:
        incorrects = list(
            filter(lambda key: not isinstance(key, (list, tuple)), defaults)
        )
        if incorrects:
            LOG.warning(
                'Defaults have not list or tuple formatted key. '
                'Try to change the key.'
            )
        for incorrect in incorrects:
            if not isinstance(incorrect, SUPPORTED_DEFAULTS_KEY_TYPE):
                pytest.fail(
                    'Unable to prepare {!r} to correct tuple format, '
                    'which required for defaults dict. '
                    'Unsuppoerted type: {!r}. Expected: {!r}'.format(
                        incorrect, type(incorrect), SUPPORTED_DEFAULTS_KEY_TYPE
                    )
                )
            else:
                value = defaults.pop(incorrect)
                defaults[(incorrect,)] = value

    fake_dict = {}
    for field_name, field in schema.fields.items():
        value = defaults.get(tuple(inners + [field_name]))
        if value:
            fake_dict[field_name] = value
            continue
        if isinstance(field, String):
            fake_dict[field_name] = "".join(
                ["Test"] + list(map(str.capitalize, field_name.split('_'))))
        elif isinstance(field, Integer):
            fake_dict[field_name] = 0
        elif isinstance(field, Nested):
            if field_name not in ['parent', 'agreements', 'children']:
                result = gen_fake_by_schema(
                    field.schema, inners=inners + [field_name, ],
                    defaults=defaults
                )
                if field.many:
                    fake_dict[field_name] = [result]
                else:
                    fake_dict[field_name] = result
    return fake_dict


def make_fake_apimethod(method, fakes_responses):
    """
    Wrapped for ApiClient method.

    :type method: str
    :type fakes_responses: dict
    """
    def fake_apimethod(api, path='', **kwargs):
        LOG.info(
            'ApiClient.%r(api=%r, base_path=%r, path=%r, kwargs=%r)',
            method, api, api.base_path, path, kwargs
        )
        key = (api.base_path, path)
        try:
            return fakes_responses[key]
        except KeyError:
            pytest.fail(
                'Request({!r}) to {!r} not found in fakes_responses: '
                '{!r}'.format(method, key, fakes_responses)
            )
    return fake_apimethod


def make_fake_mock_method(name, method_result):
    def fake_method(*args, **kwargs):
        LOG.info(
            '%s(args=%r, kwargs=%r) -> %r', name, args, kwargs, method_result
        )
        return method_result
    return fake_method


def process_request_wrapper(
        method, expected_exception=None, expected_value_checker=None
):
    @functools.wraps(method)
    def wrappen(*args, **kwargs):
        try:
            value = method(*args, **kwargs)
            if expected_value_checker is not None:
                expected_value_checker(value)
            return value
        except Exception as ex:
            if expected_exception is None:
                pytest.fail(
                    'Unexpected error was raised ({!r}). '
                    'And not covered.'.format(ex)
                )
            elif not isinstance(ex, expected_exception):
                pytest.fail(
                    'Unexpected error was raised ({!r}). Expected: {!r}'.format(
                        ex, expected_exception
                    )
                )
            else:
                raise
    return wrappen


main_defaults = {
    ('product', 'id'): "PRD-063-065-206",
    ('asset', 'product', 'id'): "PRD-063-065-206",
}


class FakeBaseObject(object):

    def __init__(self, **kwargs):
        self._data = kwargs

    def __getitem__(self, item):
        return self._data[item]

    def __getattr__(self, item):
        if item not in self._data:
            raise AttributeError
        return self._data[item]

    def to_dict(self):
        return self._data

    def __repr__(self):
        return '{self.__class__.__name__}(data={self._data})'.format(self=self)


class FakeProject(FakeBaseObject):
    pass


class FakeQuotas(FakeBaseObject):
    pass


class FakeRole(FakeBaseObject):
    pass


class ClientAttrMock(object):

    def __init__(self, parent_name, name, data):
        self._parent_name = parent_name
        self._name = name
        self._data = data

    def __getattr__(self, item):
        key = '{}.{}'.format(self._name, item)
        result = None
        if key in self._data:
            result = self._data[key]
        elif any([_.startswith(key) for _ in self._data]):
            result = ClientAttrMock(self._name, item, self._data)
        else:
            pytest.fail('"{}.{}" not mocked.'.format(self._parent_name, key))
        LOG.info('KEY: %r -> %r', key, result)
        return result


class OpenstackClientMock(object):

    def __init__(self, name, fake_methods=None, fake_attrs=None):
        self._name = name

        if fake_attrs is None:
            fake_attrs = ()
        if fake_methods is None:
            fake_methods = ()

        _data = {}
        for fake_method_path, method_result in fake_methods:
            _data[fake_method_path] = make_fake_mock_method(
                fake_method_path, method_result)
        for fake_attr_name, fake_attr_result in fake_attrs:
            _data[fake_attr_name] = fake_attr_result
        self._data = _data

    def __getattr__(self, item):
        default = ClientAttrMock(self._name, item, self._data)
        return self._data.get(item, default) if self._data else default


@pytest.mark.parametrize(
    "additional_defaults,expected_raise", (
            ({('status',): 'ready', }, SubmitUsageFile),
            ({('status',): 'pending', }, AcceptUsageFile),
            ({}, SkipRequest),
    ),
)
def test_process_usage_files(additional_defaults, expected_raise):
    defaults_ = copy.deepcopy(main_defaults)
    defaults_.update(additional_defaults)

    usage_file_schema = UsageFileSchema()
    fake_usage_file_dict = gen_fake_by_schema(
        usage_file_schema, defaults=defaults_
    )

    fake_api_get_responses = {
        ('usage/files', ''): (json.dumps([fake_usage_file_dict]), 200)
    }

    with patch(
            'cloudblue_connector.ConnectorConfig',
            return_value=ConnectorConfig(file='config-usage.json.example')
    ), patch(
            'cloudblue_connector.connector.KeystoneClient',
            return_value=OpenstackClientMock('KeystoneClient', (
                ('roles.find', [MagicMock()]),
            ))
    ), patch(
            'connect.resources.base.ApiClient.get',
            new=make_fake_apimethod('get', fake_api_get_responses)
    ), patch(
            'connect.resources.base.ApiClient.post',
            new=make_fake_mock_method('post', None)
    ), patch(
        'cloudblue_connector.UsageFileAutomation.process_request',
        new=process_request_wrapper(
            UsageFileAutomation.process_request,
            expected_exception=expected_raise)
    ):
        process_usage_files()


def make_value_type_checker(expected_type_instance):
    def wrp(value):
        if not isinstance(value, expected_type_instance):
            pytest.fail(
                'Unexpected instance ({!r} after execution. '
                'Expected: {!r}'.format(value, expected_type_instance)
            )
    return wrp


LIMIT_ITEMS = [
    {'mpn': _, 'quantity': 1, 'params': []} for _ in (
        'CPU_limit', 'Storage_limit', 'RAM_limit',
        'Floating_IP_limit', 'LB_limit',
        'K8S_limit')
]


@pytest.mark.parametrize(
    "additional_defaults,others_kwargs", (
        (
            {('type',): 'purchase', ('asset', 'items', ): LIMIT_ITEMS},
            {
                'expected_value_checker': make_value_type_checker(
                    ActivationTemplateResponse)
            }
        ),
        (
            {('type',): 'resume', ('asset', 'items', ): LIMIT_ITEMS},
            {
                'expected_value_checker': make_value_type_checker(
                    ActivationTemplateResponse)
            }
        ),
        (
            {('type',): 'change', ('asset', 'items', ): LIMIT_ITEMS},
            {
                'expected_value_checker': make_value_type_checker(
                    ActivationTemplateResponse)
            }
        ),
        (
            {('type',): 'suspend', ('asset', 'items', ): LIMIT_ITEMS},
            {
                'expected_value_checker': make_value_type_checker(
                    ActivationTileResponse)
            }
        ),
        (
            {('type',): 'cancel', ('asset', 'items', ): LIMIT_ITEMS},
            {
                'expected_value_checker': make_value_type_checker(
                    ActivationTileResponse)
            }
        ),
        (
            {('type',): 'skip', ('asset', 'items', ): LIMIT_ITEMS},
            {'expected_exception': SkipRequest}
        ),
    )
)
def test_process_fulfillment(additional_defaults, others_kwargs):
    defaults_ = copy.deepcopy(main_defaults)
    defaults_.update(additional_defaults)

    fulfilschema_instance = FulfillmentSchema()
    fake_fulfilschema_dict = gen_fake_by_schema(
        fulfilschema_instance, defaults=defaults_
    )
    conversationschema_instance = ConversationSchema()
    fake_conversationschema_dict = gen_fake_by_schema(
        conversationschema_instance, defaults=defaults_
    )
    converstationmessageschema_instance = ConversationMessageSchema()
    fake_converstationmessageschema_dict = gen_fake_by_schema(
        converstationmessageschema_instance, defaults=defaults_
    )
    fake_get_responses = {
        ('requests', ''): (
            json.dumps([fake_fulfilschema_dict]), 200),
        ('conversations', ''): (
            json.dumps([fake_conversationschema_dict]), 200),
        ('conversations', 'TestId'): (
            json.dumps(fake_conversationschema_dict), 200)
    }
    fake_post_responses = {
        ('conversations/TestId/messages', ''): (
            json.dumps(fake_converstationmessageschema_dict), 201
        ),
        ('requests', 'TestId/approve/'): (None, 201)
    }
    fake_put_responses = {
        ('requests', 'TestId'): (None, 200),
    }
    with patch(
            'cloudblue_connector.ConnectorConfig',
            return_value=ConnectorConfig(file='config.json.example')
    ), patch(
            'cloudblue_connector.connector.KeystoneClient',
            return_value=OpenstackClientMock('KeystoneClient', (
                    ('roles.find', FakeRole(id=1)),
                    ('roles.revoke', None),
                    ('roles.grant', None),
                    ('role_assignments.list', [MagicMock()]),
                    ('domains.list', [MagicMock()]),
                    ('domains.update', MagicMock()),
                    ('projects.create', MagicMock()),
                    ('users.create', MagicMock())
            ))
    ), patch(
            'cloudblue_connector.connector.CinderClient',
            return_value=OpenstackClientMock('CinderClient', (
                    ('quotas.get', FakeQuotas()),
                    ('quotas.update', FakeQuotas()),
            ))
    ), patch(
            'cloudblue_connector.connector.NeutronClient',
            return_value=OpenstackClientMock('NeutronClient', (
                ('show_quota_details', {'quota': {'floatingip': {'limit': 0}}}),
                ('update_quota', None)
            ))
    ), patch(
            'cloudblue_connector.connector.NovaClient',
            return_value=OpenstackClientMock('NovaClient', (
                ('quotas.get', FakeQuotas()),
                ('quotas.update', FakeQuotas()),
            ))
    ), patch(
            'cloudblue_connector.connector.MagnumClient',
            return_value=OpenstackClientMock('MagnumClient', (
                ('quotas.get', FakeQuotas(hard_limit=0, in_use=0)),
                ('quotas.create', FakeQuotas()),
                ('quotas.update', FakeQuotas()),
            ))
    ), patch(
            'cloudblue_connector.connector.OctaviaClient',
            return_value=OpenstackClientMock('OctaviaClient', (
                ('quota_show', {'load_balancer': 0}),
                ('quota_set', None),
            ))
    ), patch(
            'connect.resources.base.ApiClient.get',
            new=make_fake_apimethod('get', fake_get_responses)
    ), patch(
            'connect.resources.base.ApiClient.post',
            new=make_fake_apimethod('post', fake_post_responses)
    ), patch(
            'connect.resources.base.ApiClient.put',
            new=make_fake_apimethod('put', fake_put_responses)
    ), patch(
            'cloudblue_connector.connector.KeystoneSession.get_endpoint',
            return_value=''
    ), patch(
        'cloudblue_connector.FulfillmentAutomation.process_request',
        new=process_request_wrapper(
            FulfillmentAutomation.process_request,
            **others_kwargs
        )
    ):
        process_fulfillment()


def _base_test_process_usage(
        additional_keystone_mock_tuples=None,
        additional_gnocchi_mock_tuples=None,
        additional_apiget_responses=None,
        additional_apipost_responses=None,
        additional_defaults=None,
        usage_file_status='',
        usagefiles_get_cnts=1,
        expected_process_value=None,
        expected_process_exception=None,
):
    defaults_ = copy.deepcopy(main_defaults)
    defaults_.update({
        ('params', 'id'): 'project_id',
        ('params', 'value'): 'TestProject',
        ('items', ): [{'mpn': _} for _ in (
            'CPU_consumption', 'Storage_consumption', 'RAM_consumption',
            'Floating_IP_consumption', 'LB_consumption',
            'K8S_consumption'
        )]
    })
    if additional_defaults:
        defaults_.update(additional_defaults)

    # POST
    fake_usagefileschema_instance = UsageFileSchema()
    fake_usagefileschema_dict = gen_fake_by_schema(
        fake_usagefileschema_instance,
        defaults={
            'name': 'Report for TestId {}'.format(
                datetime.utcnow().strftime('%Y-%m-%d')
            ),
            'product': {'id': 'PRD-063-065-206'},
            'contract': {'id': 'TestId'},
            'description': '',
            'status': usage_file_status
        }
    )
    fake_post_responses = {
        ('listings', ''): (json.dumps(fake_usagefileschema_dict), 201),
    }

    # GET
    assetschema_instance = AssetSchema()
    fake_assetschema_dict = gen_fake_by_schema(
        assetschema_instance, defaults=defaults_)
    defaults_terminated = dict(defaults_)
    defaults_terminated[('status',)] = 'terminated'
    fake_assetschema_dict_terminated = gen_fake_by_schema(
        assetschema_instance, defaults=defaults_terminated)
    usagefiles_get_list = []
    for i in range(usagefiles_get_cnts):
        usagefiles_get_list.append(fake_usagefileschema_dict)
    fake_get_responses = {
        (
            'assets?in(status,(active))'
            '&in(product.id,(PRD-063-065-206))',
            ''
        ): (json.dumps([fake_assetschema_dict]), 200),
        ('usage/files', ''): (
            json.dumps(usagefiles_get_list), 200
        ),
        (
            'assets?in(status,(suspended,terminated))'
            '&in(product.id,(PRD-063-065-206))'
            '&gt(updated,2020-06-24T17:47:38.787420)',
            ''
        ): (json.dumps([fake_assetschema_dict_terminated]), 200),
    }
    if additional_apiget_responses:
        fake_get_responses.update(additional_apiget_responses)
    if additional_apipost_responses:
        fake_post_responses.update(additional_apipost_responses)

    # KeystoneClient
    keystone_mock_data_tuples = (
        ('roles.find', [MagicMock()]),
        ('projects.update', None),
    )
    if additional_keystone_mock_tuples:
        keystone_mock_data_tuples += \
            additional_keystone_mock_tuples
    keystone_client_mock = OpenstackClientMock(
        'KeystoneClient', keystone_mock_data_tuples
    )

    # GnocchiClient
    gnocchi_mock_data_tuples = (
        ('metric.aggregation', [{'measures': []}]),
    )
    if additional_gnocchi_mock_tuples:
        gnocchi_mock_data_tuples += \
            additional_gnocchi_mock_tuples
    gnocchi_client_mock = OpenstackClientMock(
        'GnocchiClient', gnocchi_mock_data_tuples
    )

    with patch(
            'cloudblue_connector.ConnectorConfig',
            return_value=ConnectorConfig(file='config-usage.json.example')
    ), patch(
            'cloudblue_connector.connector.KeystoneClient',
            return_value=keystone_client_mock
    ), patch(
            'cloudblue_connector.connector.GnocchiClient',
            return_value=gnocchi_client_mock
    ), patch(
            'connect.resources.base.ApiClient.get',
            new=make_fake_apimethod('get', fake_get_responses)
    ), patch(
            'connect.resources.base.ApiClient.post',
            new=make_fake_apimethod('post', fake_post_responses)
    ), patch(
            'cloudblue_connector.connector.KeystoneSession.get_endpoint',
            return_value=''
    ), patch(
        'cloudblue_connector.UsageAutomation.process_request',
        new=process_request_wrapper(
            UsageAutomation.process_request,
            expected_exception=expected_process_exception,
            expected_value_checker=expected_process_value
        )
    ), patch('cloudblue_connector.datetime') as mock_dt:
        mock_dt.utcnow = MagicMock(
            return_value=datetime(2020, 6, 29, 17, 47, 38, 787420))
        process_usage()


def test_process_usage_project_have_empty_confirmed():
    additional_keystone_mock_tuples = (
        ('projects.get', FakeProject(
            id='TestProject',
            last_usage_report_time=(
                    datetime.utcnow() - timedelta(days=4)
            ).strftime('%Y-%m-%d'),
            last_usage_report_confirmed=''
        )),
    )
    _base_test_process_usage(
        additional_keystone_mock_tuples=additional_keystone_mock_tuples
    )


@pytest.mark.parametrize(
    "usage_file_status", (
            'processing', 'draft', 'uploading', 'invalid', 'rejected', ''
    ),
)
def test_process_usage_project_have_false_confirmed(usage_file_status):
    additional_keystone_mock_tuples = (
        ('projects.get', FakeProject(
            id='TestProject',
            last_usage_report_time=(
                    datetime.utcnow() - timedelta(days=4)
            ).strftime('%Y-%m-%d'),
            last_usage_report_confirmed=False
        )),
    )
    _base_test_process_usage(
        additional_keystone_mock_tuples=additional_keystone_mock_tuples,
        usage_file_status=usage_file_status,
    )


def test_process_usage_project_is_none():
    additional_keystone_mock_tuples = (
        ('projects.get', None),
    )
    _base_test_process_usage(
        additional_keystone_mock_tuples=additional_keystone_mock_tuples
    )


def test_process_usage_project_report_date_incorrect():
    additional_keystone_mock_tuples = (
        ('projects.get', FakeProject(
            id='TestProject',
            last_usage_report_time='2020-asd-12',
            last_usage_report_confirmed=False
        )),
    )
    _base_test_process_usage(
        additional_keystone_mock_tuples=additional_keystone_mock_tuples
    )


def test_process_usage_found_3_usage_files():
    additional_keystone_mock_tuples = (
        ('projects.get', FakeProject(
            id='TestProject',
            last_usage_report_time=(
                    datetime.utcnow() - timedelta(days=4)
            ).strftime('%Y-%m-%d'),
            last_usage_report_confirmed=False
        )),
    )
    try:
        _base_test_process_usage(
            additional_keystone_mock_tuples=additional_keystone_mock_tuples,
            usagefiles_get_cnts=3,
            expected_process_exception=Exception
        )
    except Exception as ex:
        if not str(ex).startswith('Found'):
            pytest.fail('Unexpected exception.')
    else:
        pytest.fail('Exception expected.')


def test_process_usage_usage_files_not_found():
    additional_keystone_mock_tuples = (
        ('projects.get', FakeProject(
            id='TestProject',
            last_usage_report_time=(
                    datetime.utcnow() - timedelta(days=4)
            ).strftime('%Y-%m-%d'),
            last_usage_report_confirmed=False
        )),
    )
    _base_test_process_usage(
        additional_keystone_mock_tuples=additional_keystone_mock_tuples,
        usagefiles_get_cnts=0,
    )
