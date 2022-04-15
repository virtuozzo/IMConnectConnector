# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from math import ceil

import pytz
from dateutil.parser import isoparse
from dateutil.relativedelta import relativedelta
from gnocchiclient.exceptions import BadRequest as GnocchiBadRequest

from cloudblue_connector.consumption.base import Consumption, AggregatedConsumption


class LoadBalancer(AggregatedConsumption):
    resource_type = 'loadbalancer'
    operation = '(aggregate count (metric network.services.lb.loadbalancer mean))'
    hourly = False


class K8saas(AggregatedConsumption):
    resource_type = 'coe_cluster'
    operation = '(aggregate count (metric magnum.cluster mean))'


class WinVM(Consumption):
    def collect_consumption(self, project, start_time, end_time):

        def calculate_rounded_period(created, deleted):
            delta = relativedelta(deleted, created)
            # round minute(s) to hour
            if delta.minutes > 0:
                delta.hours += 1
            return delta.hours + delta.days * 24

        # get images of type 'windows'
        images_list = self.get_images_list(os_type="windows")
        if len(images_list) == 0:
            return 0

        instances = []
        marker = None
        page_limit = 100
        while True:
            page = self.gnocchi_client.resource.search(
                resource_type='instance',
                query="project_id={} and ({}) and ({})".format(
                    project.id,
                    " or ".join("image_ref=" + img.get('id') for img in images_list),
                    'deleted_at=null or (deleted_at>"' + start_time.isoformat() + '")'
                ),
                limit=page_limit,
                marker=marker
            )
            instances.extend(page)
            if len(page) == page_limit:
                marker = page[-1].get('id')
            else:
                break

        start_time_aware = pytz.timezone(pytz.utc.zone).localize(start_time)
        end_time_aware = pytz.timezone(pytz.utc.zone).localize(end_time)
        vm_count = 0
        for instance in instances:
            created_at = isoparse(instance.get('created_at'))
            deleted_at = isoparse(instance.get('deleted_at')) if instance.get('deleted_at') else end_time_aware

            # round dates if necessary, to fit into interval
            if deleted_at > end_time_aware:
                deleted_at = end_time_aware
            if created_at < start_time_aware:
                created_at = start_time_aware

            if created_at >= end_time_aware:
                # VM not created yet or already deleted
                continue
            else:
                period_round = calculate_rounded_period(created_at, deleted_at)

                try:
                    measures = self.gnocchi_client.aggregates.fetch(
                        operations="(aggregate sum (metric vcpus mean))",
                        resource_type="instance", search="id={}".format(instance.get('id')),
                        start=start_time, stop=end_time
                    ).get('measures', {}).get('aggregated', [])
                except GnocchiBadRequest:
                    # means metric NotFound
                    measures = []
                values = [m[-1] for m in measures] or [1]
                vcpus_average = sum(values) / len(values)

                self.logger.debug("VM usage=%s, vcpus average: %s for: %s '%s'", period_round, vcpus_average,
                                  instance.get('id'), instance.get('display_name'))

                vm_count += ceil(period_round * vcpus_average)

        return vm_count
