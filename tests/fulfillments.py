# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import copy
import json
import logging
from datetime import datetime, timedelta

import pytest
from connect.exceptions import SkipRequest, FailRequest, InquireRequest
from connect.models import ActivationTemplateResponse, ActivationTileResponse
from connect.models.schemas import AssetRequestSchema, ConversationSchema, ConversationMessageSchema, TierConfigSchema
from mock import patch, MagicMock

from cloudblue_connector.automation import FulfillmentAutomation
from cloudblue_connector.connector import ConnectorConfig
from cloudblue_connector.runners import process_fulfillment
from .data import MAIN_DEFAULTS, LIMIT_ITEMS
from .helpers.fake_methods import make_fake_apimethod, process_request_wrapper, make_value_type_checker
from .helpers.fake_objects import gen_fake_by_schema, FakeRole, FakeQuotas, FakeDomain, FakeProject, FakeUser
from .helpers.mocks import OpenstackClientMock

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def _base_test_process_fulfillment(additional_defaults, additional_mock_data, others_kwargs, config):
    defaults_ = copy.deepcopy(MAIN_DEFAULTS)
    defaults_.update(additional_defaults)

    fake_fulfillment = gen_fake_by_schema(AssetRequestSchema(), defaults=defaults_)
    fake_conversation = gen_fake_by_schema(ConversationSchema(), defaults=defaults_)
    fake_conversation_message = gen_fake_by_schema(ConversationMessageSchema(), defaults=defaults_)
    fake_tier_config = gen_fake_by_schema(TierConfigSchema(), defaults=defaults_)

    fake_get_responses = {
        ('requests?in(asset.product.id,(PRD-063-065-206,PRD-022-814-775))&eq(status,pending)&limit=1000', ''):
            (json.dumps([fake_fulfillment]), 200),
        ('conversations', ''):
            (json.dumps([fake_conversation]), 200),
        ('conversations', 'TestId'):
            (json.dumps(fake_conversation), 200),
        ('tier/configs?in(product.id,(PRD-063-065-206,PRD-022-814-775))&eq(account.id,TestId)', ''):
            (json.dumps([fake_tier_config]), 200),
    }
    fake_post_responses = {
        ('conversations/TestId/messages', ''): (json.dumps(fake_conversation_message), 201),
        ('requests', 'TestId/approve/'): (None, 201),
        ('requests', 'TestId/fail/'): (None, 201),
        ('requests', 'TestId/inquire/'): (None, 201)
    }
    fake_put_responses = {
        ('requests', 'TestId'): (None, 200),
    }

    keystone_mock_data = {
        'roles.find': FakeRole(id=1),
        'roles.revoke': None,
        'roles.grant': None,
        'role_assignments.list': [MagicMock()],
        'domains.list': [MagicMock()],
        'domains.update': MagicMock(),
        'projects.create': MagicMock(),
        'users.create': MagicMock()
    }
    if 'keystone_mock' in additional_mock_data:
        keystone_mock_data.update(additional_mock_data.get('keystone_mock'))

    with patch(
        'cloudblue_connector.runners.ConnectorConfig',
        return_value=config
    ), patch(
        'cloudblue_connector.connector.KeystoneClient',
        return_value=OpenstackClientMock('KeystoneClient', keystone_mock_data)
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
        'cloudblue_connector.runners.FulfillmentAutomation.process_request',
        new=process_request_wrapper(FulfillmentAutomation.process_request, **others_kwargs)
    ):
        process_fulfillment()


@pytest.mark.parametrize(
    "additional_defaults,additional_mock_data,others_kwargs",
    (
        # No "partner_id" parameter in tier1 config
        (
            {('type',): 'purchase', ('asset', 'items',): []},
            {'keystone_mock': {'domains.list': []}},
            {'expected_exception': SkipRequest}
        ),
        # partner_id" parameter exists but value not specified in tier1 config
        (
            {('type',): 'purchase', ('asset', 'items',): [], ('params', ): [{'value': None, 'id': 'partner_id'}]},
            {'keystone_mock': {'domains.list': []}},
            {'expected_exception': SkipRequest}
        ),
        # partner_id" parameter value set, but no domain with that description in cloud
        (
            {('type',): 'purchase', ('asset', 'items',): [],
             ('params',): [{'value': 'TestDomain', 'id': 'partner_id'}]},
            {'keystone_mock': {'domains.list': []}},
            {'expected_exception': SkipRequest}
        ),
        # partner_id" parameter value set, domain with that description found in cloud
        (
            {('type',): 'purchase', ('asset', 'items',): LIMIT_ITEMS,
             ('params',): [{'value': 'TestDomain', 'id': 'partner_id'}]},
            {'keystone_mock': {'domains.list': [FakeDomain(description='TestDomain', id='TestDomain')],
                               'domains.get': FakeDomain(description='TestDomain', id='TestDomain')}},
            {'expected_value_checker': make_value_type_checker(ActivationTemplateResponse)}
        ),
        # resume disabled project
        (
            {('type',): 'resume', ('asset', 'items',): LIMIT_ITEMS,
             ('params',): [{'id': 'partner_id', 'value': 'TestDomain'}],
             ('asset', 'params',):
                 [
                     {'id': 'domain_id', 'value': 'TestDomainId'},
                     {'id': 'domain_name', 'value': 'TestDomainName'},
                     {'id': 'password', 'value': 'Password'},
                     {'id': 'project_id', 'value': 'TestProjectId'},
                     {'id': 'project', 'value': 'TestProjectName'},
                     {'id': 'user_id', 'value': 'TestProjectUserId'},
                     {'id': 'user', 'value': 'TestProjectUser'},
                ]},
            {'keystone_mock': {
                'domains.list': [FakeDomain(description='TestDomain', name='TestDomain', id='TestDomain')],
                'domains.get': FakeDomain(description='TestDomain', name='TestDomain', id='TestDomain'),
                'projects.get': FakeProject(
                    id='TestProjectId',
                    last_usage_report_time=(datetime.utcnow() - timedelta(days=24)).strftime('%Y-%m-%d'),
                    last_usage_report_confirmed=True,
                    enabled=False,
                    update=MagicMock()
                ),
                'projects.update': None,
                'users.update': FakeUser(id='TestProjectUser')}},
            {'expected_value_checker': make_value_type_checker(ActivationTemplateResponse)}
        ),
    )
)
def test_process_fulfillment_payg(additional_defaults, additional_mock_data, others_kwargs):
    # For PAYG model need to modify defaults in Config
    config = ConnectorConfig(file='config.json.example', report_usage=False)
    config._misc['domainCreation'] = False
    config._misc['imageUpload'] = False
    _base_test_process_fulfillment(additional_defaults, additional_mock_data, others_kwargs, config)


@pytest.mark.parametrize(
    "additional_defaults,additional_mock_data,others_kwargs",
    (
        # Request needs migration
        (
            {('type',): 'purchase', ('asset', 'params',): [{'id': 'migration_info', 'value': 'true'}]},
            {},
            {'expected_exception': SkipRequest}
        ),
        # No limits
        (
            {('type',): 'purchase', ('asset', 'items',): []},
            {},
            {'expected_exception': FailRequest}
        ),
        # RAM limit is incorrect, cpu_limit lower than zero
        (
            {('type',): 'purchase', ('asset', 'items',): [
                {'mpn': 'CPU_limit', 'quantity': -1, 'params': [{'id': 'item_limit', 'value': '20'}]},
                {'mpn': 'RAM_limit', 'quantity': 10, 'params': [{'id': 'item_limit', 'value': '9'}]}]},
            {},
            {'expected_exception': FailRequest}
        ),
        # Cannot create project
        (
            {('type',): 'purchase', ('asset', 'items',): LIMIT_ITEMS,
             ('asset', 'params',): [{'id': 'project', 'value_error': '', 'constraints': {}}]},
            {'keystone_mock': {'projects.create': None}},
            {'expected_value_checker': make_value_type_checker(ActivationTemplateResponse),
             'expected_exception': InquireRequest}
        ),
        # Cannot create user
        (
            {('type',): 'purchase', ('asset', 'items',): LIMIT_ITEMS,
             ('asset', 'params',): [{'id': 'user', 'value_error': '', 'constraints': {}}]},
            {'keystone_mock': {'users.create': None}},
            {'expected_value_checker': make_value_type_checker(ActivationTemplateResponse),
             'expected_exception': InquireRequest}
        ),
        # Cannot create project and user
        (
            {('type',): 'purchase', ('asset', 'items',): LIMIT_ITEMS,
             ('asset', 'params',): [{'id': 'project', 'value_error': '', 'constraints': {}},
                                    {'id': 'user', 'value_error': '', 'constraints': {}}]},
            {'keystone_mock': {'projects.create': None, 'users.create': None}},
            {'expected_value_checker': make_value_type_checker(ActivationTemplateResponse),
             'expected_exception': InquireRequest}
        ),
        (
            {('type',): 'purchase', ('asset', 'items',): LIMIT_ITEMS},
            {},
            {'expected_value_checker': make_value_type_checker(ActivationTemplateResponse)}
        ),
        (
            {('type',): 'resume', ('asset', 'items',): LIMIT_ITEMS},
            {},
            {'expected_value_checker': make_value_type_checker(ActivationTemplateResponse)}
        ),
        (
            {('type',): 'change', ('asset', 'items',): LIMIT_ITEMS},
            {},
            {'expected_value_checker': make_value_type_checker(ActivationTemplateResponse)}
        ),
        (
            {('type',): 'suspend', ('asset', 'items',): LIMIT_ITEMS},
            {},
            {'expected_value_checker': make_value_type_checker(ActivationTileResponse)}
        ),
        (
            {('type',): 'cancel', ('asset', 'items',): LIMIT_ITEMS},
            {},
            {'expected_value_checker': make_value_type_checker(ActivationTileResponse)}
        ),
        (
            {('type',): 'skip', ('asset', 'items',): LIMIT_ITEMS},
            {},
            {'expected_exception': SkipRequest}
        ),
    )
)
def test_process_fulfillment(additional_defaults, additional_mock_data, others_kwargs):
    config = ConnectorConfig(file='config.json.example', report_usage=False)
    _base_test_process_fulfillment(additional_defaults, additional_mock_data, others_kwargs, config)
