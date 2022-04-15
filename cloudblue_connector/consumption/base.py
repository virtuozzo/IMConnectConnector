# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from gnocchiclient.exceptions import BadRequest as GnocchiBadRequest

from cloudblue_connector.connector import ConnectorMixin
from cloudblue_connector.core import getLogger


class Consumption(ConnectorMixin):
    """Base class for all consumption collectors"""

    def __init__(self):
        self.logger = getLogger(self.__class__.__name__)


class AggregatedConsumption(Consumption):
    resource_type = None
    operation = None
    # by default, only hourly measures are considered
    hourly = True
    rate = 1

    def collect_consumption(self, project, start_time, end_time):
        try:
            measures = self.gnocchi_client.aggregates.fetch(
                operations=self.operation, resource_type=self.resource_type,
                search="project_id={}".format(project.id),
                start=start_time, stop=end_time
            ).get('measures', {}).get('aggregated', [])
        except GnocchiBadRequest:
            # means metric NotFound
            measures = []

        return self.get_value(measures)

    def get_value(self, measures):
        hours = 1
        if self.hourly:
            # full value is only every hour
            measures = [m for m in measures if m[0].minute == 0]
        else:
            measures = [m for m in measures]
            hours = max(
                len([m for m in measures if m[0].minute == 0]),
                hours
            )

        values = [m[-1] for m in measures]
        if not values:
            values = [0]

        if self.hourly:
            return int(sum(values) / self.rate)
        else:
            return int(((float(sum(values)) / len(values)) * hours) / self.rate)


class Zero(Consumption):
    def collect_consumption(self, *args):
        return 0
