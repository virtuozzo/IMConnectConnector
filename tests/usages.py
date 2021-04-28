# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import copy
import json
import logging
from datetime import datetime, timedelta

import pytest
from connect.models.schemas import UsageFileSchema, AssetSchema
from mock import patch, MagicMock

from cloudblue_connector.automation.usage import UsageAutomation
from cloudblue_connector.runners import ConnectorConfig, process_usage
from .data import MAIN_DEFAULTS, PROJECT_DEFAULTS, USAGE_DEFAULTS, PAYG_ADDITIONAL_USAGE_DEFAULTS, TESTS_DATA
from .helpers.fake_methods import make_fake_apimethod, process_request_wrapper
from .helpers.fake_objects import FakeProject, gen_fake_by_schema
from .helpers.mocks import OpenstackClientMock, OpenstackClientParametrizedMock

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def _base_test_process_usage(
        additional_keystone_mock_tuples=None,
        additional_gnocchi_mock_data=None,
        additional_glance_mock_tuples=None,
        additional_apiget_responses=None,
        additional_apipost_responses=None,
        additional_defaults=None,
        usage_file_status='',
        usage_files_get_cnts=1,
        expected_process_value=None,
        expected_process_exception=None,
):
    defaults_ = copy.deepcopy(MAIN_DEFAULTS)
    defaults_.update(USAGE_DEFAULTS)
    if additional_defaults:
        defaults_.update(additional_defaults)

    # POST
    fake_usage_file = gen_fake_by_schema(
        UsageFileSchema(),
        defaults={
            ('name',): 'Report for TestId {}'.format(
                datetime.utcnow().strftime('%Y-%m-%d')
            ),
            ('product',): {'id': 'PRD-063-065-206'},
            ('contract',): {'id': 'TestId'},
            ('description',): '',
            ('status',): usage_file_status
        }
    )
    fake_post_responses = {
        ('listings', ''): (json.dumps(fake_usage_file), 201),
    }

    # GET
    fake_asset = gen_fake_by_schema(AssetSchema(), defaults=defaults_)
    defaults_terminated = dict(defaults_)
    defaults_terminated[('status',)] = 'terminated'
    fake_asset_terminated = gen_fake_by_schema(AssetSchema(), defaults=defaults_terminated)
    usagefiles_get_list = []
    for i in range(usage_files_get_cnts):
        usagefiles_get_list.append(fake_usage_file)
    fake_get_responses = {
        ('assets?in(status,(active))&in(product.id,(PRD-063-065-206))', ''):
            (json.dumps([fake_asset]), 200),
        ('usage/files?in(product_id,(PRD-063-065-206))&eq(name,Report for TestId {})&limit=10'
            .format((datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d')), ''):
            (json.dumps(usagefiles_get_list), 200),
        ('assets?in(status,(suspended,terminated))&in(product.id,(PRD-063-065-206))&gt(updated,2020-06-24T17:47:38.787420)', ''):
            (json.dumps([fake_asset_terminated]), 200),
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
        keystone_mock_data_tuples += additional_keystone_mock_tuples
    keystone_client_mock = OpenstackClientMock('KeystoneClient', keystone_mock_data_tuples)

    # GnocchiClient
    gnocchi_mock_data = {
        'metric.aggregation': {(): [{'measures': []}]},
        'aggregates.fetch': {(): {'measures': {}}},
    }
    if additional_gnocchi_mock_data:
        gnocchi_mock_data.update(additional_gnocchi_mock_data)
    gnocchi_client_mock = OpenstackClientParametrizedMock('GnocchiClient', gnocchi_mock_data)

    # GlanceClient
    glance_mock_data_tuples = (
        ('images.list', []),
    )
    if additional_glance_mock_tuples:
        glance_mock_data_tuples += additional_glance_mock_tuples
    glance_client_mock = OpenstackClientMock('GlanceClient', glance_mock_data_tuples)

    with patch(
        'cloudblue_connector.runners.ConnectorConfig',
        return_value=ConnectorConfig(file='config.json.example', report_usage=True)
    ), patch(
        'cloudblue_connector.connector.KeystoneClient',
        return_value=keystone_client_mock
    ), patch(
        'cloudblue_connector.connector.GnocchiClient',
        return_value=gnocchi_client_mock
    ), patch(
        'cloudblue_connector.connector.GlanceClient',
        return_value=glance_client_mock
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
        'cloudblue_connector.runners.UsageAutomation.process_request',
        new=process_request_wrapper(
            UsageAutomation.process_request,
            expected_exception=expected_process_exception,
            expected_value_checker=expected_process_value
        )
    ), patch('cloudblue_connector.runners.datetime') as mock_dt:
        mock_dt.utcnow = MagicMock(return_value=datetime(2020, 6, 29, 17, 47, 38, 787420))
        process_usage()


@pytest.mark.parametrize(
    "additional_glance_mock_tuples,additional_gnocchi_mock_data",
    (
        # Windows VMS cpu consumption data
        (
            (('images.list', TESTS_DATA['images_list']),),
            {'resource.search': {
                (('resource_type', 'instance'),): TESTS_DATA['windows_vms'],
                (('resource_type', 'instance_network_interface'),): []
            }}
        ),
        # Traffic consumption data
        (
            (),
            {'resource.search': {
                (('resource_type', 'instance'),): [
                    {"display_name": "vm1",
                     "created_at": (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d') + "T17:06:26+00:00",
                     "deleted_at": None}],
                (('resource_type', 'instance_network_interface'),): [
                    {'id': '11111111-1111-1111-1111-111111111113'}]},
             'aggregates.fetch': {
                (): {'measures': {}},
                (('search', 'id=11111111-1111-1111-1111-111111111113'),):
                    {'measures':
                     {'11111111-1111-1111-1111-111111111113':
                      {'network.outgoing.bytes': {'mean': TESTS_DATA['traffic']}}}}
            }}
        )
    )
)
def test_process_usage_payg(additional_glance_mock_tuples, additional_gnocchi_mock_data):
    _base_test_process_usage(
        additional_keystone_mock_tuples=(('projects.get', FakeProject(**PROJECT_DEFAULTS)),),
        additional_defaults=PAYG_ADDITIONAL_USAGE_DEFAULTS,
        additional_glance_mock_tuples=additional_glance_mock_tuples,
        additional_gnocchi_mock_data=additional_gnocchi_mock_data
    )


@pytest.mark.parametrize(
    "additional_keystone_mock_tuples",
    (
        # Project have empty confirmed report date
        (('projects.get', FakeProject(**PROJECT_DEFAULTS).update(last_usage_report_confirmed='')),),
        # Project is none
        (('projects.get', None),),
        # Project report date is incorrect
        (('projects.get', FakeProject(**PROJECT_DEFAULTS).update(last_usage_report_time='2020-asd-12')),),
        # Project terminated
        (('projects.get', FakeProject(**PROJECT_DEFAULTS).update(
            stop_usage_report_time=(datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%d'),
            start_usage_report_time=(datetime.utcnow() - timedelta(days=6)).strftime('%Y-%m-%d'))),),
    )
)
def test_process_usage(additional_keystone_mock_tuples):
    _base_test_process_usage(
        additional_keystone_mock_tuples=additional_keystone_mock_tuples
    )


@pytest.mark.parametrize(
    "usage_file_status",
    ('processing', 'draft', 'uploading', 'invalid', 'rejected', ''),
)
def test_process_usage_project_have_false_confirmed(usage_file_status):
    _base_test_process_usage(
        additional_keystone_mock_tuples=(('projects.get', FakeProject(**PROJECT_DEFAULTS)),),
        usage_file_status=usage_file_status,
    )


def test_process_usage_project_id_is_none():
    _base_test_process_usage(
        additional_defaults={('params', 'id'): 'project_id', ('params', 'value'): 'None'}
    )


def test_process_usage_found_3_usage_files():
    try:
        _base_test_process_usage(
            additional_keystone_mock_tuples=(('projects.get', FakeProject(**PROJECT_DEFAULTS)),),
            usage_files_get_cnts=3,
            expected_process_exception=Exception
        )
    except Exception as ex:
        if not str(ex).startswith('Found'):
            pytest.fail('Unexpected exception.')
    else:
        pytest.fail('Exception expected.')


def test_process_usage_usage_files_not_found():
    _base_test_process_usage(
        additional_keystone_mock_tuples=(('projects.get', FakeProject(**PROJECT_DEFAULTS)),),
        usage_files_get_cnts=0,
    )
