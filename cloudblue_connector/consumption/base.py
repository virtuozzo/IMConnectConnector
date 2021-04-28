# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from cloudblue_connector.connector import ConnectorMixin
from cloudblue_connector.core import getLogger


class Consumption(ConnectorMixin):
    """Base class for all consumption collectors"""

    def __init__(self):
        self.logger = getLogger(self.__class__.__name__)


class Zero(Consumption):
    def collect_consumption(self, *args):
        return 0
