# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import warnings
from datetime import datetime, timedelta

from connect.rql import Query

from .automation import FulfillmentAutomation, UsageAutomation, UsageFileAutomation
from .connector import ConnectorConfig

# Enable processing of deprecation warnings
warnings.simplefilter('default')


def process_usage(project_id=None):
    """Create UsageFiles for active Assets"""

    ConnectorConfig(file='/etc/cloudblue-connector/config.json', report_usage=True)
    mngr = UsageAutomation(project_id=project_id)
    # check that keystone works
    mngr.find_role('admin')
    # last day usage reporting for suspended/terminated assets
    five_days_ago = datetime.utcnow() - timedelta(days=5)
    filters = Query().greater('updated', five_days_ago.isoformat()).in_('status', ['suspended', 'terminated'])
    mngr.process(filters)

    # every day usage reporting
    filters = Query().in_('status', ['active'])
    mngr.process(filters)
    return mngr.usages


def process_usage_files():
    """Confirm all created UsageFiles"""

    ConnectorConfig(file='/etc/cloudblue-connector/config.json', report_usage=True)
    mngr = UsageFileAutomation()
    # check that keystone works
    mngr.find_role('admin')
    mngr.process()
    return mngr.files


def process_fulfillment():
    """Process all new Fulfillments"""

    ConnectorConfig(file='/etc/cloudblue-connector/config.json', report_usage=False)
    mngr = FulfillmentAutomation()
    # check that keystone works
    mngr.find_role('admin')
    mngr.process()
    return mngr.fulfillments
