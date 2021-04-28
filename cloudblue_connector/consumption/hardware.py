# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from cloudblue_connector.consumption.base import Consumption


class Hardware(Consumption):
    resource_name = None
    rate = 1

    def collect_consumption(self, project, start_time, end_time):
        groups = self.gnocchi_client.metric.aggregation(
            self.resource_name, groupby='project_id',
            aggregation='mean', reaggregation='sum', granularity=300,
            query={"=": {"project_id": project.id}}, fill=0,
            start=start_time, stop=end_time)
        measures = next(iter(groups), {}).get('measures', [])
        # full value is only every hour
        measures = [m for m in measures if m[0].minute == 0]
        values = [m[-1] for m in measures]

        return int(sum(values) / self.rate)


class CPU(Hardware):
    resource_name = 'vcpus'


class RAM(Hardware):
    resource_name = 'memory'
    rate = 1024


class Storage(Hardware):
    resource_name = 'volume.size'
