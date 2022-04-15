# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
from datetime import datetime, timedelta

SUPPORTED_DEFAULTS_KEY_TYPE = (str,)

MAIN_DEFAULTS = {
    ('product', 'id'): "PRD-063-065-206",
    ('asset', 'product', 'id'): "PRD-063-065-206",
}

PROJECT_DEFAULTS = {
    'id': 'TestProjectId',
    'last_usage_report_time': (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d'),
    'last_usage_report_confirmed': False
}

USAGE_DEFAULTS = {
    ('params', 'id'): 'project_id',
    ('params', 'value'): 'TestProjectId',
    ('items',): [{'mpn': _} for _ in (
        'CPU_consumption', 'Storage_consumption', 'RAM_consumption',
        'Floating_IP_consumption', 'LB_consumption',
        'K8S_consumption'
    )]
}

PAYG_ADDITIONAL_USAGE_DEFAULTS = {
    ('items',): [{'mpn': _} for _ in (
        'CPU_consumption', 'Storage_consumption', 'RAM_consumption',
        'Floating_IP_consumption', 'LB_consumption', 'K8S_consumption',
        # For PAYG model
        'Win_VM_consumption', 'Outgoing_Traffic_consumption'
    )]
}

LIMIT_ITEMS = [
    {'mpn': _, 'quantity': 1, 'params': []} for _ in (
        'CPU_limit', 'Storage_limit', 'RAM_limit',
        'Floating_IP_limit', 'LB_limit',
        'K8S_limit')
]

ASSET_PARAMS_ITEMS = [
    {'id': 'domain_id', 'value': 'TestDomainId'},
    {'id': 'domain_name', 'value': 'TestDomainName'},
    {'id': 'password', 'value': 'Password'},
    {'id': 'project_id', 'value': 'TestProjectId'},
    {'id': 'project', 'value': 'TestProjectName'},
    {'id': 'user_id', 'value': 'TestProjectUserId'},
    {'id': 'user', 'value': 'TestProjectUser'},
]

__all__ = [
    'SUPPORTED_DEFAULTS_KEY_TYPE',
    'MAIN_DEFAULTS',
    'PROJECT_DEFAULTS',
    'USAGE_DEFAULTS',
    'PAYG_ADDITIONAL_USAGE_DEFAULTS',
    'LIMIT_ITEMS',
    'ASSET_PARAMS_ITEMS',
]
