# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import copy
import json
import logging

import pytest
from connect.exceptions import SubmitUsageFile, AcceptUsageFile, SkipRequest
from connect.models.schemas import UsageFileSchema
from mock import patch, MagicMock

from cloudblue_connector.automation import UsageFileAutomation
from cloudblue_connector.connector import ConnectorConfig
from cloudblue_connector.runners import process_usage_files
from .data import MAIN_DEFAULTS
from .helpers.fake_methods import make_fake_apimethod, make_fake_mock_method, process_request_wrapper
from .helpers.fake_objects import gen_fake_by_schema
from .helpers.mocks import OpenstackClientMock

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


@pytest.mark.parametrize(
    "additional_defaults,expected_raise",
    (
        ({('status',): 'ready', }, SubmitUsageFile),
        ({('status',): 'pending', }, AcceptUsageFile),
        ({}, SkipRequest),
    ),
)
def test_process_usage_files(additional_defaults, expected_raise):
    defaults_ = copy.deepcopy(MAIN_DEFAULTS)
    defaults_.update(additional_defaults)

    fake_usage_file = gen_fake_by_schema(UsageFileSchema(), defaults=defaults_)
    fake_api_get_responses = {
        ('usage/files?in(status,(ready,pending))&in(product_id,(PRD-063-065-206))&limit=1000', ''):
            (json.dumps([fake_usage_file]), 200)
    }

    with patch(
        'cloudblue_connector.runners.ConnectorConfig',
        return_value=ConnectorConfig(file='config.json.example', report_usage=True)
    ), patch(
        'cloudblue_connector.connector.KeystoneClient',
        return_value=OpenstackClientMock('KeystoneClient', (('roles.find', [MagicMock()]),))
    ), patch(
        'connect.resources.base.ApiClient.get',
        new=make_fake_apimethod('get', fake_api_get_responses)
    ), patch(
        'connect.resources.base.ApiClient.post',
        new=make_fake_mock_method('post', None)
    ), patch(
        'cloudblue_connector.runners.UsageFileAutomation.process_request',
        new=process_request_wrapper(UsageFileAutomation.process_request, expected_exception=expected_raise)
    ):
        process_usage_files()
