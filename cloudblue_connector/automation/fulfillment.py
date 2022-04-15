# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

import random
import string
from datetime import datetime, timedelta

from connect import resources
from connect.config import Config
from connect.exceptions import SkipRequest, InquireRequest, FailRequest
from connect.resources import Directory
from connect.rql import Query

from cloudblue_connector.connector import ConnectorMixin
from cloudblue_connector.core.logger import context_log
from cloudblue_connector.quota import BadQuota, CinderQuotaUpdater, NovaQuotaUpdater, \
    NeutronQuotaUpdater, OctaviaQuotaUpdater, MagnumQuotaUpdater


# not used in production
def pwgen(length=24):
    """Generates pseudo-random password"""

    # letters not found in python3
    _PWCHARS = string.ascii_letters + string.digits

    return ''.join(random.sample(_PWCHARS, length))


class FulfillmentAutomation(resources.FulfillmentAutomation, ConnectorMixin):
    """This is the automation engine for Fulfillments processing"""

    fulfillments = []

    def get_tier_partner_data(self, account_id=None):
        """Look for domain name in tier1 configuration data. `partner_id` keeps this information for us"""

        filters = Query().equal('account.id', account_id)
        configs = list(Directory().list_tier_configs(filters))

        for config in configs:
            for param in config.params:
                if param.id == 'partner_id':
                    return param

        return None

    @context_log
    def process_request(self, request):
        """Each new Fulfillment is processed by this function"""

        conf = Config.get_instance()

        # store all processed request for debug
        self.fulfillments.append(request)

        if request.needs_migration():
            # Skip request if it needs migration
            # (migration is performed by an external service)
            self.logger.info('Skipping request %s because it needs migration.', request.id)
            raise SkipRequest()

        if self.test_marketplace_requests_filter(conf, request.id, request.asset.marketplace):
            raise SkipRequest()

        param_partner_id = None
        if not conf.misc['domainCreation']:
            self.logger.info('Request "%s" needs domain that created manually. '
                             'Lookup for domain name in tier1 configuration data...', request.id)
            partner_data = self.get_tier_partner_data(request.asset.tiers.tier1.id)
            if partner_data is None:
                raise SkipRequest('Misconfiguration: there is no "partner_id" parameter in tier1 "%s" config'
                                  % request.asset.tiers.tier1.id)
            elif partner_data.value is None:
                raise SkipRequest(message='Please specify "partner_id" parameter value in tier1 "%s" config'
                                          % request.asset.tiers.tier1.id)
            param_partner_id = partner_data.value
            self.logger.info('Got the following domain data from tier1 config: "%s"' % param_partner_id)

        project = None

        params = {p.id: p for p in request.asset.params}

        # get account parameters from Asset
        param_domain_name = params.get('domain_name')
        param_domain_id = params.get('domain_id')
        param_project_id = params.get('project_id')
        param_user_id = params.get('user_id')

        self.logger.info("Request type: %s", request.type)
        self.logger.info("param_partner_id: %s, param_domain_name: %s, param_domain_id: %s, "
                         "param_project_id: %s, param_user_id: %s",
                         param_partner_id, param_domain_name and param_domain_name.value,
                         param_domain_id and param_domain_id.value,
                         param_project_id and param_project_id.value, param_user_id and param_user_id.value)

        if request.type in ('purchase', 'resume', 'change'):
            if not conf.misc['domainCreation']:
                # if domain creation is set to manual, needs to check:
                #   - if domain with such description exists in the cloud, go to next steps
                #   - if not - return nice message and set request status
                domain = self.get_existing_domain(partner_id=param_partner_id)
                if domain is None:
                    raise SkipRequest('Request "%s" needs domain that created manually. '
                                      'Cannot find any domain with description "%s"' % (request.id, param_partner_id))
            else:
                # create domain
                customer_id = request.asset.tiers.customer.id
                customer_name = request.asset.tiers.customer.name
                domain = self.create_or_update_domain(
                    name=customer_id, description=customer_name,
                    domain_id=param_domain_id and param_domain_id.value)

            # create project
            project_description = request.asset.id
            project_name = params.get('project') and params['project'].value or project_description
            project = self.create_project(
                project_id=param_project_id and param_project_id.value,
                name=project_name, domain=domain,
                description=project_description, enabled=False)

            # create user
            user_description = request.asset.id
            user_name = params.get('user') and params['user'].value or user_description
            user_password = params.get('password') and params['password'].value or pwgen()
            user = self.create_user(
                user_id=param_user_id and param_user_id.value,
                name=user_name, domain=domain,
                description=user_description,
                password=user_password)

            # check conflicts
            conflicts = []
            if project is None:
                if params.get('project'):
                    params['project'].value_error = 'This project name is already taken, please choose a different name'
                    params['project'].constraints = None
                    conflicts.append(params['project'])

            if user is None:
                if params.get('user'):
                    params['user'].value_error = 'This user name is already taken, please choose a different name'
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

            self.update_parameters(request.id, params_update)

            # assign roles
            user_roles = ['project_admin']
            if conf.misc['imageUpload']:
                user_roles.append('image_upload')
            self.assign_user_roles(user, project, roles=user_roles)

            # configure quotas
            def get_item_limit(item):
                limit_param = next((p for p in item.params if p.id == 'item_limit'), None)
                try:
                    return int(limit_param.value)
                except Exception:
                    return -1

            def get_quota(item, error=FailRequest("ERROR: REQUESTED LIMITS ARE HIGHER THEN HARD LIMITS")):
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
            self.logger.info('VIP requested items %r', items)
            try:
                # get quota limits from Asset parameters
                cpu_quota = get_quota(items.get('cpu_limit', items.get("cpu_consumption", None)))
                ram_quota = get_quota(items.get('ram_limit', items.get("ram_consumption", None)))
                vol_quota = get_quota(items.get('storage_limit', items.get("storage_consumption", None)))

                # fail request if basic limits are missing
                if 0 in (cpu_quota, ram_quota, vol_quota):
                    raise FailRequest("CPU, RAM, and Storage limits cannot be 0")

                fip_quota = get_quota(items.get('floating_ip_limit', items.get("floating_ip_consumption", None)))
                lb_quota = get_quota(items.get('lbaas_limit', items.get("lb_consumption", None)))
                k8s_quota = get_quota(items.get('k8saas_limit', items.get("k8s_consumption", None)))

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
                        'ram': (ram_quota * 1024 if ram_quota > 0 else ram_quota)})
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
                                self.logger.exception("Unable to rollback quotas")
                        if rollback_error:
                            raise Exception('Unable to setup quotas')
                        raise FailRequest('\n'.join(errors))
                except Exception as e:
                    self.logger.exception("Unable to setup quotas")
                    for u in updaters:
                        try:
                            u.rollback()
                        except Exception:
                            self.logger.exception("Unable to rollback quotas")
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
                self.logger.exception("Unable to setup quotas")
                raise

            rv = self.get_answer(request.asset.product.id, 'grant')
            if not project.enabled:
                # if project was suspended a long time ago we open new usage
                # reporting interval setting start_usage_report_time. But if
                # stop_report_time is not equal last_report_time then there
                # was no report closing previous usage reporting interval.
                # So the gap between stop and start will be ignored.
                stop_report_time = self.get_stop_report_time(request, project)
                last_report_time, _ = self.get_last_report_time(request, project)
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
        elif request.type == 'suspend':
            pid = param_project_id and param_project_id.value or None
            uid = param_user_id and param_user_id.value or None

            self.operate_servers(pid, 'stop')
            self.suspend_user(uid)
            self.suspend_project(request, pid)

            return self.get_answer(request.asset.product.id, 'revoke') or ''
        elif request.type == 'cancel':
            pid = param_project_id and param_project_id.value or None
            uid = param_user_id and param_user_id.value or None
            data_retention_period = datetime.utcnow() + timedelta(days=conf.data_retention_period)
            description = 'SCHEDULED FOR DELETION AFTER {}'.format(data_retention_period.strftime('%Y-%m-%d'))

            # TODO implement automatic cleanup after Asset cancellation
            self.operate_servers(pid, 'shelve', description=description)
            self.suspend_user(uid, description=description)
            self.suspend_project(request, pid, description=description)

            # TODO: special template for this case?
            return self.get_answer(request.asset.product.id, 'revoke') or ''

        self.logger.warning("Do not know what to do with such request")
        raise SkipRequest()
