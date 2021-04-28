# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import logging

import pytest

from cloudblue_connector.connector import ConnectorConfig
from cloudblue_connector.core.logger import PasswordFilter
from .data import TESTS_DATA

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def test_config_incorrect_initialization():
    # Config file not specified
    with pytest.raises(SystemExit) as e:
        ConnectorConfig()
    assert e.type == SystemExit
    assert e.value.code == 1

    # Not existing config file specified
    with pytest.raises(SystemExit) as e:
        ConnectorConfig(file='config.json.not_exists')
    assert e.type == SystemExit
    assert e.value.code == 1


def test_logger_filtering(caplog):
    ConnectorConfig(file='config.json.example')

    ext_logger = logging.getLogger('tests.connector_components')
    ext_logger.addFilter(PasswordFilter())

    for m in TESTS_DATA['log_messages']:
        LOG.info(m)

    for record in caplog.records:
        if any(record.message.find(p) != -1 for p in TESTS_DATA['log_passwords']):
            pytest.fail("Passwords found in captured log records")
