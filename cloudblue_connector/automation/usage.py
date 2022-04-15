# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from datetime import datetime, timedelta

from connect import resources
from connect.config import Config
from connect.exceptions import ServerError
from connect.models import UsageFile, Product, Contract, UsageRecord
from connect.rql import Query
from keystoneclient.exceptions import NotFound as KeystoneNotFound

from cloudblue_connector.automation.usage_file import UsageFileAutomation
from cloudblue_connector.connector import ConnectorMixin
from cloudblue_connector.consumption import CPU, Storage, RAM, FloatingIP, LoadBalancer, K8saas, WinVM,\
    OutgoingTraffic, Zero
from cloudblue_connector.core.logger import context_log


class UsageAutomation(resources.UsageAutomation, ConnectorMixin):
    """Automates reporting of Usage Files"""

    usages = []

    def __init__(self, project_id=None):
        super(UsageAutomation, self).__init__()
        self.project_id = project_id

    def get_project(self, request):
        project_id = next(p for p in request.params
                          if p.id == 'project_id').value
        if not project_id:
            self.logger.error('%s: project id is None', request.id)
            return
        try:
            return self.keystone_client.projects.get(project_id)
        except KeystoneNotFound:
            self.logger.error('%s-%s: project not found', request.id, project_id)

    def update_last_report_time(self, project, report_time, confirmed=False):
        """Store last repost time in project metadata"""

        self.keystone_client.projects.update(
            project, last_usage_report_time=report_time.isoformat(),
            last_usage_report_confirmed=confirmed)

    def _format_usage_record_id(self, project, report_time, mpn):
        return "{}-{}-{}".format(project.id, report_time.isoformat(), mpn)

    @context_log
    def process_request(self, request):
        """Generate UsageFile for each active Asset"""

        # store each processed request for debug
        self.usages.append(request)

        if self.test_marketplace_requests_filter(Config.get_instance(), request.id, request.marketplace):
            return

        today = datetime.utcnow() - timedelta(minutes=10)
        name_format = 'Report for {asset} {date}'

        project = self.get_project(request)
        if not project:
            return

        stop_report_time = self.get_stop_report_time(request, project)
        start_report_time = self.get_start_report_time(request, project)
        self.logger.info("Start report time: %s, stop report time: %s", start_report_time, stop_report_time)
        if request.status in ['suspended', 'terminated'] and not stop_report_time:
            self.logger.info("%s-%s: asset usage reporting was stopped without stop report time label", request.id, project.id)
            return

        last_report_time, confirmed = self.get_last_report_time(request, project)
        report_time = last_report_time + timedelta(days=1)
        report_time = report_time.replace(hour=0, minute=0, second=0, microsecond=0)
        self.logger.info("Last report time: %s, report time: %s, confirmed: %s", last_report_time, report_time, confirmed)

        if self.project_id is not None and self.project_id != project.id:
            self.logger.info("project_id=%s is not the same as project.id=%s, skip it", self.project_id, project.id)
            return

        # check that previous report has passed validation
        if confirmed is False:
            usage_files = UsageFileAutomation()
            try:
                report_date = last_report_time.strftime('%Y-%m-%d')
                report_name = name_format.format(asset=request.id, date=report_date)

                filters = Query().equal('name', report_name).limit(10)
                if self.config.products:
                    filters.in_('product_id', self.config.products)
                found = usage_files.list(filters)

                found = [f for f in found or [] if f.status != 'deleted']
                self.logger.debug("Found usage files: %s", found)

                if found:
                    if len(found) > 2:
                        raise Exception("Found multiple reports with name %s" % report_name)

                    report = found[0]

                    if report.status in ('processing', 'draft', 'uploading'):
                        self.logger.info("%s-%s: usage report '%s' is being processed", request.id, project.id, report_name)
                        return

                    if report.status in ('invalid', 'rejected'):
                        # we have to wait when user remove invalid report
                        self.logger.error("%s-%s: failed usage report '%s' found", request.id, project.id, report_name)
                        return

                    self.update_last_report_time(project, last_report_time, confirmed=True)
                else:
                    report_time = last_report_time

            except ServerError:
                # this section is useless but left for future development
                raise

        if request.status in ['suspended', 'terminated']:
            if stop_report_time and last_report_time < stop_report_time <= report_time:
                self.logger.info("%s-%s: sending last report (%s)", request.id, project.id, request.status)
                report_time = stop_report_time

        if start_report_time and last_report_time < start_report_time < report_time:
            last_report_time = start_report_time

        if report_time > today and self.project_id is None:
            self.logger.info("%s-%s: usage is already reported", request.id, project.id)
            return

        usage_file = UsageFile(
            name=name_format.format(asset=request.id, date=report_time.strftime('%Y-%m-%d')),
            product=Product(id=request.product.id),
            contract=Contract(id=request.contract.id),
            description=name_format.format(asset=request.id, date=report_time.strftime('%Y-%m-%d')),
        )

        # report for each day since last report date
        self.logger.info("%s-%s: creating report from %s to %s", request.id, project.id, last_report_time, report_time)
        items = {item.mpn: item for item in request.items}
        usage_records = self.collect_usage_records(items, project, last_report_time, report_time)
        self.submit_usage(usage_file=usage_file, usage_records=usage_records)

        if report_time > today:
            # when project id is specified we allow to send usage for today
            # but don't update last report time
            return

        self.update_last_report_time(project, report_time)

    def collect_usage_records(self, items, project, start_time, end_time):
        """Create UsageRecord object for each type of resources"""

        consumptions = {
            'CPU_consumption': CPU(),
            'Storage_consumption': Storage(),
            'RAM_consumption': RAM(),
            'Floating_IP_consumption': FloatingIP(),
            'LB_consumption': LoadBalancer(),
            'K8S_consumption': K8saas(),
            'Win_VM_consumption': WinVM(),
            'Outgoing_Traffic_consumption': OutgoingTraffic()
        }

        conf = Config.get_instance()
        consumptions.update({mpn: Zero() for mpn in conf.misc.get('report_zero_usage', [])})

        def known_resources(item):
            return item in consumptions

        def collect_item_consumption(item):
            return self.create_record(
                project, start_time, end_time, item,
                consumptions.get(item).collect_consumption(project, start_time, end_time))

        return map(collect_item_consumption, filter(known_resources, items))

    def create_record(self, project, start_time, end_time, mpn, value):
        """Create UsageRecord object"""

        self.logger.info("add '%s' value %s", mpn, value)
        return UsageRecord(
            # should we store this object somewhere?
            usage_record_id=self._format_usage_record_id(project, end_time, mpn),
            item_search_criteria='item.mpn',
            # CPU_consumption, Storage_consumption, RAM_consumption
            item_search_value=mpn,
            quantity=value,
            start_time_utc=start_time.strftime('%Y-%m-%d %H:%M:%S'),
            end_time_utc=end_time.strftime('%Y-%m-%d %H:%M:%S'),
            asset_search_criteria='parameter.project_id',
            asset_search_value=project.id,
        )

    # Listing in not available for TestMarket, we implement
    # our own version of Asset listing using Directory API
    # to have same code for TaskMarket and production
    def list(self, filters=None):
        """List all active Assets"""
        from connect.resources.directory import Directory
        filters = filters or self.filters()
        assets = list(Directory().list_assets(filters=filters))

        for a in assets:
            # contract's marketplace is emtpy
            # let's use from asset
            a.contract.marketplace = a.marketplace
            # provider is used in debug logs
            a.provider = a.connection.provider

        return assets
