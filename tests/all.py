# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
from mock import patch
patcher_once = patch('cloudblue_connector.core.decorators.once', lambda x: x).start()
patcher_memoize = patch('cloudblue_connector.core.decorators.memoize', lambda x: x).start()

from .connector_components import test_logger_filtering,\
    test_config_incorrect_initialization
from .fulfillments import test_process_fulfillment,\
    test_process_fulfillment_payg,\
    test_process_fulfillment_test_mode
from .usage_files import test_process_usage_files
from .usages import test_process_usage, \
    test_process_usage_test_mode, \
    test_process_usage_payg, \
    test_process_usage_project_have_false_confirmed, \
    test_process_usage_project_id_is_none, \
    test_process_usage_found_3_usage_files, \
    test_process_usage_usage_files_not_found
