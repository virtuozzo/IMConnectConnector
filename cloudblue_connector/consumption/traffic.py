# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from datetime import timedelta

from gnocchiclient.exceptions import BadRequest as GnocchiBadRequest

from cloudblue_connector.consumption.base import Consumption


class FloatingIP(Consumption):
    def collect_consumption(self, project, start_time, end_time):
        try:
            measures = self.gnocchi_client.aggregates.fetch(
                operations="(aggregate count (metric ip.floating mean))",
                resource_type="network", search="project_id={}".format(project.id),
                start=start_time, stop=end_time
            ).get('measures', {}).get('aggregated', [])
        except GnocchiBadRequest:
            # means metric NotFound
            measures = []

        # full value is only every hour
        measures = [m for m in measures if m[0].minute == 0]
        values = [m[-1] for m in measures]
        return int(sum(values))


class OutgoingTraffic(Consumption):
    def collect_consumption(self, project, start_time, end_time):
        instances = []
        marker = None
        page_limit = 100
        while True:
            page = self.gnocchi_client.resource.search(
                resource_type='instance',
                query="project_id={} and ({})".format(
                    project.id,
                    'deleted_at=null or (deleted_at>"' + start_time.isoformat() + '")'),
                limit=page_limit,
                marker=marker
            )
            instances.extend(page)
            if len(page) == page_limit:
                marker = page[-1].get('id')
            else:
                break
        self.logger.info("Instances: %s", instances)

        bytes_out = 0.0
        for instance in instances:
            interfaces = []
            page = self.gnocchi_client.resource.search(
                resource_type='instance_network_interface',
                query="instance_id={}".format(instance.get('id')),
                limit=page_limit,
                marker=None
            )
            interfaces.extend(page)
            self.logger.info("Instance id='%s', name='%s' interfaces: %s",
                             instance.get('id'), instance.get('display_name'), interfaces)

            for interface in interfaces:
                try:
                    # for traffic we need to get wholeday stats, starting and ending in midnight
                    measures = self.gnocchi_client.aggregates.fetch(
                        operations="(metric network.outgoing.bytes mean)",
                        resource_type="generic", search="id={}".format(interface.get('id')),
                        start=start_time, stop=end_time + timedelta(minutes=5)
                    ).get('measures', {}).get(interface.get('id'), {}).get('network.outgoing.bytes', {}).get('mean', [])
                except GnocchiBadRequest:
                    # means metric NotFound
                    measures = []

                bytes_out_if = 0.0
                if len(measures):
                    previous_value = measures[0][2]
                    for m in measures:
                        if previous_value < m[2]:
                            bytes_out_if += m[2] - previous_value
                        previous_value = m[2]

                self.logger.info("Outgoing traffic for instance id='%s' on interface id='%s' name='%s': %sB",
                                 instance.get('id'), interface.get('id'), interface.get('name'), bytes_out_if)
                bytes_out += bytes_out_if

        # convert to MB
        bytes_out = round(bytes_out / (1024 * 1024), 4)
        self.logger.info("Outgoing traffic for project id='%s': %sMB", project.id, bytes_out)
        return bytes_out
