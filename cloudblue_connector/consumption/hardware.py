# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from gnocchiclient.exceptions import BadRequest as GnocchiBadRequest

from cloudblue_connector.consumption.base import Consumption, AggregatedConsumption


class CPU(AggregatedConsumption):
    resource_type = 'instance'
    operation = '(aggregate sum (metric vcpus mean))'


class RAM(AggregatedConsumption):
    resource_type = 'instance'
    operation = '(aggregate sum (metric memory mean))'
    rate = 1024


class Storage(Consumption):
    resource_name = 'volume.'

    def collect_consumption(self, project, start_time, end_time):
        metrics = {
            'resource_name1': self.resource_name + 'size',
            'resource_name2': self.resource_name + 'snapshot.size',
        }

        try:
            measures1 = self.gnocchi_client.aggregates.fetch(
                operations='(aggregate sum (metric {} mean))'.format(metrics.get('resource_name1')),
                resource_type='volume',
                search="project_id={}".format(project.id),
                start=start_time, stop=end_time
            ).get('measures', {}).get('aggregated', [])
        except GnocchiBadRequest:
            # means metric NotFound
            measures1 = []

        try:
            measures2 = self.gnocchi_client.aggregates.fetch(
                operations='(aggregate sum (metric {} mean))'.format(metrics.get('resource_name2')),
                resource_type='volume',
                search="project_id={}".format(project.id),
                start=start_time, stop=end_time
            ).get('measures', {}).get('aggregated', [])
        except GnocchiBadRequest:
            # means metric NotFound
            measures2 = []

        result = 0
        for measures in (measures1, measures2):
            hours = max(
                len([m for m in measures if m[0].minute == 0]),
                1
            )
            values = [m[-1] for m in measures]
            if not values:
                values = [0]

            result += (float(sum(values)) / len(values)) * hours

        return int(result)
