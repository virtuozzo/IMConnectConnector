# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from .updater import BadQuota, CinderQuotaUpdater, NovaQuotaUpdater, NeutronQuotaUpdater, MagnumQuotaUpdater, \
    OctaviaQuotaUpdater

__all__ = [
    'BadQuota',
    'CinderQuotaUpdater',
    'NovaQuotaUpdater',
    'NeutronQuotaUpdater',
    'MagnumQuotaUpdater',
    'OctaviaQuotaUpdater'
]
