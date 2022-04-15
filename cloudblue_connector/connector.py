# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

import copy
import itertools
import json
import os
import sys
from datetime import datetime

import dateutil.parser
from cinderclient.client import Client as CinderClient
from cinderclient.exceptions import BadRequest as CinderBadRequest
from connect.config import Config
from connect.models import ActivationTemplateResponse, ActivationTileResponse
from glanceclient.client import Client as GlanceClient
from gnocchiclient.client import Client as GnocchiClient
from keystoneauth1 import identity
from keystoneauth1.session import Session as KeystoneSession
from keystoneclient.exceptions import BadRequest as KeystoneBadRequest
from keystoneclient.exceptions import Conflict as KeystoneConflict
from keystoneclient.exceptions import EndpointNotFound as KeystoneEndpointNotFound
from keystoneclient.exceptions import NotFound as KeystoneNotFound
from keystoneclient.v3.client import Client as KeystoneClient
from magnumclient.client import Client as MagnumClient
from neutronclient.v2_0.client import Client as NeutronClient
from novaclient.client import Client as NovaClient
from octaviaclient.api.v2.octavia import OctaviaAPI as OctaviaClient

from cloudblue_connector.core import getLogger
from cloudblue_connector.core.decorators import once, memoize, log_exception, MISSING

LOG = getLogger("Connector")


class ConnectorConfig(Config):
    """Extension of CloudBlue connect config model"""

    @staticmethod
    def _read_config_value(config, key, default=MISSING):
        if default is MISSING:
            if key not in config:
                raise ValueError('"{}" not found in the config file'.format(key))
        val = config.get(key, default)
        if isinstance(val, dict):
            if default is not MISSING:
                for k in default:
                    if k not in val:
                        val[k] = default[k]
            return val
        return val.encode('utf-8') if not isinstance(val, (str, list, int)) else val

    def __init__(self, **kwargs):
        filename = kwargs.get('file')
        if filename and not os.path.exists(filename):
            LOG.error('Configuration file "%s" not found.', filename)
            sys.exit(1)

        if filename:
            # read infrastructure parameters
            with open(filename) as config_file:
                config = json.loads(config_file.read())
            self._infra_keystone_endpoint = self._read_config_value(config, 'infraKeystoneEndpoint')
            self._infra_user = self._read_config_value(config, 'infraUser')
            self._infra_password = self._read_config_value(config, 'infraPassword')
            self._infra_project = self._read_config_value(config, 'infraProject', 'admin')
            self._infra_domain = self._read_config_value(config, 'infraDomain', 'Default')
            self._templates = self._read_config_value(config, 'templates', {})
            self._misc = self._read_config_value(
                config, 'misc', {
                    'domainCreation': True,
                    'imageUpload': True,
                    'hidePasswordsInLog': True,
                    'testMarketplaceId': None,
                    'testMode': False
                })
            self._data_retention_period = int(self._read_config_value(config, 'dataRetentionPeriod', 15))
            # prepare data for connect
            api_url = self._read_config_value(config, 'apiEndpoint')
            api_key = self._read_config_value(config, 'apiKey')
            products = self._read_config_value(config, 'products')
            if kwargs.get('report_usage', False):
                products = self._read_config_value(config, 'report_usage')
            products = [products] if isinstance(products, str) and products else products or []
            super(ConnectorConfig, self).__init__(api_url=api_url, api_key=api_key, products=products)
        else:
            LOG.error('Configuration file not specified')
            sys.exit(1)

    @property
    def infra_keystone_endpoint(self):
        return self._infra_keystone_endpoint

    @property
    def infra_user(self):
        return self._infra_user

    @property
    def infra_project(self):
        return self._infra_project

    @property
    def infra_domain(self):
        return self._infra_domain

    @property
    def templates(self):
        return copy.deepcopy(self._templates)

    @property
    def infra_password(self):
        return self._infra_password

    @property
    def misc(self):
        return copy.deepcopy(self._misc)

    @property
    def data_retention_period(self):
        return self._data_retention_period


class ConnectorMixin(object):
    @memoize
    def get_answer(self, product, answer):
        """Get template object specified in the Config"""
        c = Config.get_instance()
        line = c.templates.get(product, {}).get(answer)
        if line is None:
            return line

        if line.startswith('TL'):
            return ActivationTemplateResponse(line)
        return ActivationTileResponse(line)

    @property
    @once
    def keystone_session(self):
        """Create KeystoneSession object using params in the Config"""

        c = Config.get_instance()
        auth = identity.v3.Password(
            auth_url=c.infra_keystone_endpoint,
            username=c.infra_user,
            project_name=c.infra_project,
            password=c.infra_password,
            user_domain_name=c.infra_domain,
            project_domain_name=c.infra_domain,
            reauthenticate=True,
        )
        return KeystoneSession(auth=auth, verify=False)

    @property
    @once
    def keystone_client(self):
        """Create KeystoneClient object using KeystoneSession"""

        c = Config.get_instance()
        return KeystoneClient(
            session=self.keystone_session,
            endpoint_override=c.infra_keystone_endpoint,
            connect_retries=2,
        )

    @property
    @once
    def cinder_client(self):
        return CinderClient(
            version='3.45',
            session=self.keystone_session,
            connect_retries=2,
        )

    @property
    @once
    def glance_client(self):
        return GlanceClient(
            version='2',
            session=self.keystone_session
        )

    @property
    @once
    def gnocchi_client(self):
        return GnocchiClient(
            version='1',
            session=self.keystone_session,
            # connect_retries=2,
        )

    @property
    @once
    def nova_client(self):
        return NovaClient(
            version='2.60',
            session=self.keystone_session,
            connect_retries=2,
        )

    @property
    @once
    def neutron_client(self):
        return NeutronClient(
            session=self.keystone_session,
            connect_retries=2,
        )

    @property
    @once
    def octavia_client(self):
        try:
            endpoint = self.keystone_session.get_endpoint(service_type='load-balancer', interface='public')
        except KeystoneEndpointNotFound:
            endpoint = None

        if endpoint is None:
            return endpoint

        return OctaviaClient(
            session=self.keystone_session,
            endpoint=endpoint,
            connect_retries=2,
        )

    @property
    @once
    def magnum_client(self):
        try:
            endpoint = self.keystone_session.get_endpoint(service_type='container-infra', interface='public')
        except KeystoneEndpointNotFound:
            endpoint = None

        if endpoint is None:
            return endpoint

        return MagnumClient(
            version='1', api_version='1.8', interface='public',
            session=self.keystone_session,
            connect_retries=2,
        )

    @memoize
    def find_role(self, name):
        """Find user role by name"""

        return self.keystone_client.roles.find(name=name)

    @log_exception
    @memoize
    def get_images_list(self, os_type=None):
        images = []
        for image in itertools.chain(self.glance_client.images.list(),
                                     self.glance_client.images.list(filters={"os_hidden": "True"})):
            if image.get("os_type") and image["os_type"] == os_type:
                images.append(image)

        LOG.debug("images of type '%s': %s", os_type, images)

        return images

    @log_exception
    def get_existing_domain(self, partner_id=None):
        domains = self.keystone_client.domains.list()
        for domain in domains:
            if domain.description == partner_id:
                return self.keystone_client.domains.get(domain.id)
        return None

    @log_exception
    def create_or_update_domain(self, name, description=None, enabled=True, domain_id=None):
        domain = None
        if domain_id:
            try:
                domain = self.keystone_client.domains.get(domain_id)
            except KeystoneNotFound:
                # domain was removed
                pass
        if domain is None:
            domains = self.keystone_client.domains.list(name=name)
            domain = domains[0] if domains else None
        if domain is None:
            try:
                return self.keystone_client.domains.create(name, description=description, enabled=enabled)
            except KeystoneConflict:
                # race protection
                domains = self.keystone_client.domains.list(name=name)
                domain = domains[0] if domains else None
        return self.keystone_client.domains.update(domain, name=name, description=description, enabled=enabled)

    def create_project(self, name, domain, description=None,
                       enabled=True, project_id=None):
        if project_id:
            try:
                return self.keystone_client.projects.get(project_id)
            except KeystoneNotFound:
                # project was removed
                return
        try:
            report_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            return self.keystone_client.projects.create(
                name, domain, description=description, enabled=enabled,
                last_usage_report_time=report_time.isoformat(),
                start_usage_report_time=report_time.isoformat(),
                last_usage_report_confirmed=True)
        except (KeystoneConflict, KeystoneBadRequest):
            # something wrong with the name
            LOG.exception('Something wrong with the requested name')

    def create_user(self, name, domain, password=None,
                    description=None, enabled=True, user_id=None):
        if user_id:
            try:
                return self.keystone_client.users.update(user_id, enabled=True)
            except KeystoneNotFound:
                # user was removed
                pass
        try:
            return self.keystone_client.users.create(
                name=name, domain=domain, password=password,
                description=description, enabled=enabled)
        except (KeystoneConflict, KeystoneBadRequest):
            LOG.exception('Something wrong with the requested name or password')

    def assign_user_roles(self, user, project, roles):
        roles = [self.find_role(role).id for role in roles]
        current_roles = [
            ra.role['id'] for ra in self.keystone_client.role_assignments.list(
                user=user, project=project)
        ]

        for role in set(current_roles) - set(roles):
            self.keystone_client.roles.revoke(role, user=user, project=project)

        for role in roles:
            self.keystone_client.roles.grant(role, user=user, project=project)

    def suspend_user(self, user_id, description=None):
        if user_id:
            try:
                self.keystone_client.users.update(user_id, enabled=False, description=description)
            except KeystoneNotFound:
                pass
        else:
            LOG.error('User id not specified')

    def suspend_project(self, request, project_id, description=None):
        if project_id:
            try:
                report_time = datetime.utcnow().replace(microsecond=0)
                params = {}
                if request.asset.status != 'suspended':
                    params['stop_usage_report_time'] = report_time.isoformat()
                self.keystone_client.projects.update(
                    project_id, enabled=False, description=description,
                    **params)
            except KeystoneNotFound:
                pass
        else:
            LOG.error('Project id not specified')

    def operate_servers(self, project_id, action, description=None):
        actions = {
            'stop': {
                'statuses': ['ACTIVE', 'ERROR'],
                'method': self.nova_client.servers.stop
            },
            'shelve': {
                'statuses': ['ACTIVE', 'SHUTOFF', 'STOPPED', 'PAUSED', 'SUSPENDED'],
                'method': self.nova_client.servers.shelve
            }
        }

        if project_id is None:
            LOG.error("Project id not specified")
            return
        if actions.get(action, None) is None:
            LOG.error("Unknown action '%s'", action)
            return

        servers_list = self.nova_client.servers.\
            list(search_opts={'all_tenants': True, 'project_id': project_id})

        for server in servers_list:
            if server.status in actions.get(action)['statuses']:
                try:
                    if description:
                        self.nova_client.servers.update(server, description=description)
                    actions.get(action)['method'](server)
                except Exception:
                    LOG.exception("Exception raised while attempt to %s server '%s' (%s)",
                                  action, server.id, server.name)
            else:
                LOG.warning("Cannot %s server '%s' (%s) because it is in '%s' status",
                            action, server.id, server.name, server.status)

    @log_exception
    def configure_storage_quotas(self, project_id, quotas):
        current_quotas = self.cinder_client.quotas.get(project_id)
        gigabytes_quotas = {key: 0 for key in current_quotas.to_dict().keys()
                            if key.startswith('gigabytes_')}

        total = 0
        for vt in quotas.keys():
            value = quotas[vt]
            if total == -1 or value == -1:
                total = -1
            else:
                total += value
            gigabytes_quotas['gigabytes_' + vt] = value
        gigabytes_quotas['gigabytes'] = total
        try:
            self.cinder_client.quotas.update(project_id, **gigabytes_quotas)
        except CinderBadRequest:
            return ""

    @log_exception
    def configure_compute_quotas(self, project_id, quotas):
        self.nova_client.quotas.update(project_id, **quotas)

    @log_exception
    def configure_network_quotas(self, project_id, quotas):
        self.neutron_client.update_quota(project_id, body=dict(quota=quotas))

    @log_exception
    def configure_lbaas_quotas(self, project_id, quotas):
        clnt = self.octavia_client
        if not clnt:
            return

        clnt.quota_set(project_id, json=dict(quota=quotas))

    def get_last_report_time(self, request, project):
        project_dict = project.to_dict()
        confirmed = project_dict.get('last_usage_report_confirmed')
        last_report_time = self._get_report_time(
            request, project, 'last_usage_report_time')
        # last report time or today
        return (last_report_time, confirmed) if last_report_time \
            else (datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0), None)

    def _get_report_time(self, request, project, field):
        project_dict = project.to_dict()
        time_str = project_dict.get(field)
        report_time = None
        try:
            report_time = dateutil.parser.parse(time_str) if time_str else None
        except Exception:
            LOG.exception('%s-%s: unable to parse "%s"', request.id, project.id, time_str)
        return report_time

    def get_stop_report_time(self, request, project):
        return self._get_report_time(request, project, 'stop_usage_report_time')

    def get_start_report_time(self, request, project):
        return self._get_report_time(request, project, 'start_usage_report_time')

    def test_marketplace_requests_filter(self, conf, request_id, marketplace):
        if conf.misc['testMarketplaceId']:
            if conf.misc['testMode'] and marketplace.id != conf.misc['testMarketplaceId']:
                LOG.warning('Skipping request %s because test mode is enabled '
                            'and request came not from test marketplace', request_id)
                return True
            if not conf.misc['testMode'] and marketplace.id == conf.misc['testMarketplaceId']:
                LOG.warning('Skipping request %s because test mode is disabled '
                            'and request came from test marketplace', request_id)
                return True
        return False
