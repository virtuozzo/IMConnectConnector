#******************************************************************************
# Copyright (c) 2020, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
#******************************************************************************

import random
import string
import warnings

from datetime import datetime, timedelta

from connect.exceptions import AcceptUsageFile, DeleteUsageFile, FailRequest, \
    InquireRequest, ServerError, SkipRequest, SubmitUsageFile
from connect.logger import logger

from connect.models import Contract, UsageRecord, UsageFile, UsageListing, \
        Product

from connect import resources

from connect.rql import Query

from .connector import getLogger

from .connector import BadQuota
from .connector import ConnectorConfig
from .connector import ConnectorMixin
from .connector import KeystoneNotFound

from .connector import CinderQuotaUpdater, NeutronQuotaUpdater, \
        NovaQuotaUpdater, MagnumQuotaUpdater, OctaviaQuotaUpdater


# Enable processing of deprecation warnings
warnings.simplefilter('default')

# Set connect log level / default level ERROR
logger.setLevel('DEBUG')

LOG = getLogger(__name__)

# letters not found in python3
_PWCHARS = string.ascii_letters + string.digits


# not used in production
def pwgen(length=24):
    """Generates pseudo-random password"""

    return ''.join(random.sample(_PWCHARS, length))


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
            LOG.error('%s: project id is None', request.id)
            return
        try:
            return self.keystone_client.projects.get(project_id)
        except KeystoneNotFound:
            LOG.error('%s-%s: project not found', request.id, project_id)

    def update_last_report_time(self, project, report_time, confirmed=False):
        """Store last repost time in project metadata"""

        self.keystone_client.projects.update(
            project, last_usage_report_time=report_time.isoformat(),
            last_usage_report_confirmed=confirmed)

    def _format_usage_record_id(self, project, report_time, mpn):
        return "{}-{}-{}".format(project.id, report_time.isoformat(), mpn)

    def process_request(self, request):
        """Generate UsageFile for each active Asset"""

        # store each processed request for debug
        self.usages.append(request)

        today = datetime.utcnow() - timedelta(minutes=10)
        name_format = 'Report for {asset} {date}'

        project = self.get_project(request)
        if not project:
            return

        stop_report_time = self.get_stop_report_time(request, project)
        start_report_time = self.get_start_report_time(request, project)
        if request.status in ['suspended', 'terminated'] \
                and not stop_report_time:
            LOG.info("%s-%s: asset usage reporting was stopped without "
                     "stop report time label", request.id, project.id)
            return

        last_report_time, confirmed = self.get_last_report_time(
            request, project)
        report_time = last_report_time + timedelta(days=1)
        report_time = report_time.replace(
            hour=0, minute=0, second=0, microsecond=0)

        if self.project_id is not None and self.project_id != project.id:
            return

        # check that previous report has passed validation
        if confirmed is False:
            usage_files = UsageFileAutomation()
            try:
                report_date = last_report_time.strftime('%Y-%m-%d')
                report_name = name_format.format(asset=request.id,
                                                 date=report_date)
                found = usage_files.list(dict(
                    usage_files.filters(), name=report_name,
                    status__in=None, limit=10,
                ))

                found = [f for f in found or [] if f.status != 'deleted']

                if found:
                    if len(found) > 2:
                        raise Exception("Found multiple reports with name %s"
                                        "" % report_name)

                    report = found[0]

                    if report.status in ('processing', 'draft', 'uploading'):
                        LOG.info("%s-%s: usage report '%s' is being processed",
                                 request.id, project.id, report_name)
                        return

                    if report.status in ('invalid', 'rejected'):
                        # we have to wait when user remove invalid report
                        LOG.error("%s-%s: failed usage report '%s' found",
                                  request.id, project.id, report_name)
                        return

                    self.update_last_report_time(project, last_report_time,
                                                 confirmed=True)
                else:
                    report_time = last_report_time

            except ServerError:
                # this section is useless but left for future development
                raise

        if request.status in ['suspended', 'terminated']:
            if stop_report_time and stop_report_time > last_report_time \
                    and stop_report_time <= report_time:
                LOG.info("%s-%s: sending last report (%s)",
                         request.id, project.id, request.status)
                report_time = stop_report_time

        if start_report_time and start_report_time > last_report_time \
                and start_report_time < report_time:
            last_report_time = start_report_time

        if report_time > today and self.project_id is None:
            LOG.info("%s-%s: usage is already reported",
                     request.id, project.id)
            return

        usage_file = UsageFile(
            name=name_format.format(
                asset=request.id, date=report_time.strftime('%Y-%m-%d')),
            product=Product(id=request.product.id),
            contract=Contract(id=request.contract.id),
            description=name_format.format(
                asset=request.id, date=report_time.strftime('%Y-%m-%d')),
        )

        # report for each day since last report date
        LOG.info("%s-%s: creating report from %s to %s",
                 request.id, project.id,
                 last_report_time, report_time)
        items = {item.mpn: item for item in request.items}
        usage_records = self.collect_usage_records(
            items, project, last_report_time, report_time)
        self.submit_usage(
            usage_file=usage_file, usage_records=usage_records)

        if report_time > today:
            # when project id is specified we allow to send usage for today
            # but don't update last report time
            return

        self.update_last_report_time(project, report_time)

    def _collect_cpu_consumption(self, project, start_time, end_time):
        groups = self.gnocchi_client.metric.aggregation(
            'vcpus', groupby='project_id',
            aggregation='mean', reaggregation='sum', granularity=300,
            query={"=":{"project_id": project.id}}, fill=0,
            start=start_time, stop=end_time)
        measures = next(iter(groups), {}).get('measures', [])
        # full value is only every hour
        measures = [m for m in measures if m[0].minute == 0]
        values = [m[-1] for m in measures]
        return int(sum(values))

    def _collect_storage_consumption(self, project, start_time, end_time):
        groups = self.gnocchi_client.metric.aggregation(
            'volume.size', groupby='project_id',
            aggregation='mean', reaggregation='sum', granularity=300,
            query={"=":{"project_id": project.id}}, fill=0,
            start=start_time, stop=end_time)
        measures = next(iter(groups), {}).get('measures', [])
        # full value is only every hour
        measures = [m for m in measures if m[0].minute == 0]
        values = [m[-1] for m in measures]
        return int(sum(values))

    def _collect_floating_ip_consumption(self, project, start_time, end_time):
        groups = self.gnocchi_client.metric.aggregation(
            'ip.floating', groupby='project_id',
            aggregation='mean', reaggregation='count', granularity=300,
            query={"=":{"project_id": project.id}}, fill=0,
            start=start_time, stop=end_time)
        measures = next(iter(groups), {}).get('measures', [])
        # full value is only every hour
        measures = [m for m in measures if m[0].minute == 0]
        values = [m[-1] for m in measures]
        return int(sum(values))

    def _collect_loadbalancer_consumption(self, project, start_time, end_time):
        groups = self.gnocchi_client.metric.aggregation(
            'network.services.lb.loadbalancer', groupby='project_id',
            aggregation='mean', reaggregation='count', granularity=300,
            query={"=":{"project_id": project.id}}, fill=0,
            start=start_time, stop=end_time)
        measures = next(iter(groups), {}).get('measures', [])
        # full value is only every hour
        measures = [m for m in measures if m[0].minute == 0]
        values = [m[-1] for m in measures]
        return int(sum(values))

    def _collect_ram_consumption(self, project, start_time, end_time):
        groups = self.gnocchi_client.metric.aggregation(
            'memory', groupby='project_id',
            aggregation='mean', reaggregation='sum', granularity=300,
            query={"=":{"project_id": project.id}}, fill=0,
            start=start_time, stop=end_time)
        measures = next(iter(groups), {}).get('measures', [])
        # full value is only every hour
        measures = [m for m in measures if m[0].minute == 0]
        values = [m[-1] for m in measures]
        return int(sum(values)/1024)

    def _collect_k8saas_consumption(self, project, start_time, end_time):
        groups = self.gnocchi_client.metric.aggregation(
            'magnum.cluster', groupby='project_id',
            aggregation='mean', reaggregation='count', granularity=300,
            query={"=":{"project_id": project.id}}, fill=0,
            start=start_time, stop=end_time)
        measures = next(iter(groups), {}).get('measures', [])
        # full value is only every hour
        measures = [m for m in measures if m[0].minute == 0]
        values = [m[-1] for m in measures]
        return int(sum(values))

    def collect_usage_records(self, items, project, start_time, end_time):
        """Create UsageRecord object for each type of resources"""

        usage_records = []
        if 'CPU_consumption' in items:
            usage_records.append(self.create_record(
                project, start_time, end_time, 'CPU_consumption',
                self._collect_cpu_consumption(
                    project, start_time, end_time)))
        if 'Storage_consumption' in items:
            usage_records.append(self.create_record(
                project, start_time, end_time, 'Storage_consumption',
                self._collect_storage_consumption(
                    project, start_time, end_time)))
        if 'RAM_consumption' in items:
            usage_records.append(self.create_record(
                project, start_time, end_time, 'RAM_consumption',
                self._collect_ram_consumption(
                    project, start_time, end_time)))
        if 'Floating_IP_consumption' in items:
            usage_records.append(self.create_record(
                project, start_time, end_time, 'Floating_IP_consumption',
                self._collect_floating_ip_consumption(
                    project, start_time, end_time)))
        if 'LB_consumption' in items:
            usage_records.append(self.create_record(
                project, start_time, end_time, 'LB_consumption',
                self._collect_loadbalancer_consumption(
                    project, start_time, end_time)))
        if 'K8S_consumption' in items:
            usage_records.append(self.create_record(
                project, start_time, end_time, 'K8S_consumption',
                self._collect_k8saas_consumption(
                    project, start_time, end_time)))
        return usage_records

    def create_record(self, project, start_time, end_time, mpn, value):
        """Create UsageRecord object"""

        LOG.info("add '%s' value %s", mpn, value)
        return UsageRecord(
            # should we store this object somewhere?
            usage_record_id=self._format_usage_record_id(
                project, end_time, mpn),
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


class UsageFileAutomation(resources.UsageFileAutomation, ConnectorMixin):
    """Automates workflow of Usage Files."""

    files = []

    def dispatch(self, request):
        try:
            super(UsageFileAutomation, self).dispatch(request)
        except Exception:
            # the error is ignored because we don't want to fail processing
            # of other UsageFiles
            LOG.exception('XXX')
        return 'skip'

    def process_request(self, request):
        """Confirme all UsafeFiles that has 'ready' status"""

        # store all processed requests for debug
        self.files.append(request)

        if request.status == 'ready':
            raise SubmitUsageFile()
        elif request.status == 'pending':
            raise AcceptUsageFile('Automatically confirmed')

        raise SkipRequest()

    def filters(self, **kwargs):
        filters = super(UsageFileAutomation, self).filters(**kwargs)
        # by default it returns only usage files in 'ready' status
        del filters['status']
        filters['status__in'] = 'ready,pending'
        if 'product_id' in filters:
            # see https://github.com/cloudblue/connect-python-sdk/pull/103
            filters['product_id__in'] = filters.pop('product_id')
        return filters


class FulfillmentAutomation(resources.FulfillmentAutomation, ConnectorMixin):
    """This is the automation engine for Fulfillments processing"""

    fulfillments = []

    def process_request(self, request):
        """Each new Fulfillment is processed by this function"""

        # store all processed request for debug
        self.fulfillments.append(request)

        if request.needs_migration():
            # Skip request if it needs migration
            # (migration is performed by an external service)
            LOG.info('Skipping request %s because it needs migration.',
                     request.id)
            raise SkipRequest()

        project = None

        params = {p.id: p for p in request.asset.params}

        # get account parameters from Asset
        param_domain_name = params.get('domain_name')
        param_domain_id = params.get('domain_id')
        param_project_id = params.get('project_id')
        param_user_id = params.get('user_id')

        if request.type in ('purchase', 'resume', 'change'):
            # creat domain
            customer_id = request.asset.tiers.customer.id
            customer_name = request.asset.tiers.customer.name
            domain = self.create_or_update_domain(
                name=customer_id, description=customer_name,
                domain_id=param_domain_id and param_domain_id.value)

            # create project
            project_description = request.asset.id
            project_name = params.get('project') and params['project'].value \
                or project_description
            project = self.create_project(
                project_id=param_project_id and param_project_id.value,
                name=project_name, domain=domain,
                description=project_description, enabled=False)

            # create user
            user_description = request.asset.id
            user_name = params.get('user') and params['user'].value \
                or user_description
            user_password = \
                params.get('password') and params['password'].value \
                or pwgen()
            user = self.create_user(
                user_id=param_user_id and param_user_id.value,
                name=user_name, domain=domain,
                description=user_description,
                password=user_password)

            # check conflicts
            conflicts = []
            if project is None:
                if params.get('project'):
                    params['project'].value_error = \
                        'This project name is already taken, ' \
                        'please choose a different name'
                    params['project'].constraints = None
                    conflicts.append(params['project'])

            if user is None:
                if params.get('user'):
                    params['user'].value_error = \
                        'This user name is already taken, ' \
                        'please choose a different name'
                    params['user'].constraints = None
                    conflicts.append(params['user'])

            if conflicts:
                if user:
                    user.delete()
                if project:
                    project.delete()
                raise InquireRequest(params=conflicts)
            if user is None:
                raise Exception('Unable to create a user')
            if project is None:
                raise Exception('Unable to create a project')

            # update params (project_id, user_id)
            params_update = []
            if param_domain_name and param_domain_name.value != domain.name:
                param_domain_name.value = domain.name
                param_domain_name.constraints = None
                params_update.append(param_domain_name)
            if param_domain_id and param_domain_id.value != domain.id:
                param_domain_id.value = domain.id
                param_domain_id.constraints = None
                params_update.append(param_domain_id)
            if param_project_id and param_project_id.value != project.id:
                param_project_id.value = project.id
                param_project_id.constraints = None
                params_update.append(param_project_id)
            if param_user_id and param_user_id.value != user.id:
                param_user_id.value = user.id
                param_user_id.constraints = None
                params_update.append(param_user_id)

            self.update_parameters(
                request.id, params_update
            )

            # assign roles
            self.assign_user_roles(
                user, project, roles=['project_admin', 'image_upload'])

            # configure quotas
            def get_item_limit(item):
                limit_param = \
                    next((p for p in item.params if p.id == 'item_limit'), None)
                try:
                    return int(limit_param.value)
                except Exception:
                    return -1

            def get_quota(item, error=FailRequest(
                    "ERROR: REQUESTED LIMITS ARE HIGHER THEN HARD LIMITS")):
                if item is None:
                    return 0
                quantity = item.quantity
                item_limit = get_item_limit(item)
                if item_limit >= 0:
                    if quantity > item_limit:
                        raise error
                if quantity < 0:
                    quantity = item_limit
                return quantity

            items = {item.mpn.lower(): item for item in request.asset.items}
            LOG.info('VIP requested items %r', items)
            try:
                # get quota limits from Asset parameters
                cpu_quota = get_quota(
                    items.get('cpu_limit', items.get("cpu_consumption", None)))
                ram_quota = get_quota(
                    items.get('ram_limit', items.get("ram_consumption", None)))
                vol_quota = get_quota(
                    items.get('storage_limit',
                              items.get("storage_consumption", None)))

                # fail request if basic limits are missing
                if 0 in (cpu_quota, ram_quota, vol_quota):
                    raise FailRequest("CPU, RAM, and Storage limits cannot be 0")

                fip_quota = get_quota(
                    items.get('floating_ip_limit',
                              items.get("floating_ip_consumption", None)))
                lb_quota = get_quota(
                    items.get('lbaas_limit',
                              items.get("lb_consumption", None)))
                k8s_quota = get_quota(
                    items.get('k8saas_limit',
                              items.get("k8s_consumption", None)))

                errors = []
                updaters = []

                def apply_quota(updater, client, quotas):
                    try:
                        u = updater(client, project.id)
                        u.update(quotas)
                        updaters.append(u)
                    except BadQuota as e:
                        errors.append(e.message)

                try:
                    # update project quotas
                    apply_quota(CinderQuotaUpdater, self.cinder_client, {
                        'gigabytes_default': vol_quota})
                    apply_quota(NovaQuotaUpdater, self.nova_client, {
                        'cores': cpu_quota,
                        'ram': (ram_quota * 1024 if ram_quota > 0
                                else ram_quota)})
                    apply_quota(NeutronQuotaUpdater, self.neutron_client, {
                        'floatingip': fip_quota})
                    apply_quota(OctaviaQuotaUpdater, self.octavia_client, {
                        'load_balancer': lb_quota})
                    apply_quota(MagnumQuotaUpdater, self.magnum_client, {
                        'hard_limit': k8s_quota})
                    if errors:
                        rollback_error = False
                        for u in updaters:
                            try:
                                u.rollback()
                            except Exception:
                                rollback_error = True
                                LOG.exception("Unable to rollback quotas")
                        if rollback_error:
                            raise Exception('Unable to setup quotas')
                        raise FailRequest('\n'.join(errors))
                except Exception as e:
                    LOG.exception("Unable to setup quotas")
                    for u in updaters:
                        try:
                            u.rollback()
                        except Exception:
                            LOG.exception("Unable to rollback quotas")
                    raise e
            except FailRequest:
                if request.type == 'purchase':
                    # remove project if we fail to process 'purchase' request
                    if project:
                        project.delete()
                        project = None
                raise
            except SkipRequest:
                raise
            except Exception:
                LOG.exception("Unable to setup quotas")
                raise

            rv = self.get_answer(request.asset.product.id, 'grant')
            if not project.enabled:
                # if project was suspended a long time ago we open new usage
                # reporting interval setting start_usage_report_time. But if
                # stop_report_time is not equal last_report_time then there
                # was no report closing previous usage reporting interval.
                # So the gap between stop and start will be ignored.
                stop_report_time = self.get_stop_report_time(
                    request, project)
                last_report_time, _ = self.get_last_report_time(
                    request, project)
                if stop_report_time != last_report_time:
                    stop_report_time = ''

                report_time = datetime.utcnow().replace(microsecond=0)
                self.keystone_client.projects.update(
                    project, enabled=True,
                    start_usage_report_time=report_time.isoformat()
                    if stop_report_time else '',
                    stop_usage_report_time=stop_report_time)
                project.update(enabled=True)
            if rv:
                return rv
        elif request.type in ('suspend', 'cancel'):
            self.suspend_project(
                request,
                param_domain_id and param_domain_id.value or None,
                param_project_id and param_project_id.value or None,
                param_user_id and param_user_id.value or None,
            )

            # TODO implement automatic cleanup after Asset cancellation
            try:
                pid = param_project_id and param_project_id.value or None
                if request.type == 'cancel' and pid:
                    self.keystone_client.projects.update(
                        pid, description='SCHEDULED FOR DELETE')
            except Exception:
                pass
            return self.get_answer(request.asset.product.id, 'revoke') or ''

        raise SkipRequest()


def process_usage(project_id=None):
    """Create UsageFiles for active Assets"""

    ConnectorConfig(file='/etc/cloudblue-connector/config-usage.json')
    mngr = UsageAutomation(project_id=project_id)
    # check that keystone works
    mngr.find_role('admin')
    # last day usage reporting for suspended/terminated assets
    five_days_ago = datetime.utcnow() - timedelta(days=5)
    filters = Query().greater(
        'updated', five_days_ago.isoformat()).in_(
            'status', ['suspended', 'terminated'])
    mngr.process(filters)

    # every day usage reporting
    filters = Query().in_('status', ['active'])
    mngr.process(filters)
    return mngr.usages


def process_usage_files():
    """Confirm all created UsageFiles"""

    ConnectorConfig(file='/etc/cloudblue-connector/config-usage.json')
    mngr = UsageFileAutomation()
    # check that keystone works
    mngr.find_role('admin')
    mngr.process()
    return mngr.files


def process_fulfillment():
    """Process all new Fulfillments"""

    ConnectorConfig(file='/etc/cloudblue-connector/config.json')
    mngr = FulfillmentAutomation()
    # check that keystone works
    mngr.find_role('admin')
    mngr.process()
    return mngr.fulfillments
