#******************************************************************************
# Copyright (c) 2020, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
#******************************************************************************

import copy
import functools
import json
import logging
import os
import sys

from datetime import datetime, timedelta
import dateutil.parser

from connect.config import Config
from connect.models import \
        ActivationTemplateResponse, ActivationTileResponse

from keystoneauth1 import identity
from keystoneauth1.session import Session as KeystoneSession
from keystoneclient.v3.client import Client as KeystoneClient
from keystoneclient.exceptions import BadRequest as KeystoneBadRequest
from keystoneclient.exceptions import Conflict as KeystoneConflict
from keystoneclient.exceptions import NotFound as KeystoneNotFound
from keystoneclient.exceptions import \
    EndpointNotFound as KeystoneEndpointNotFound

from cinderclient.client import Client as CinderClient
from cinderclient.exceptions import BadRequest as CinderBadRequest

from gnocchiclient.client import Client as GnocchiClient

from neutronclient.v2_0.client import Client as NeutronClient
from neutronclient.common.exceptions import BadRequest as NeutronBadRequest

from novaclient.client import Client as NovaClient
from novaclient.exceptions import BadRequest as NovaBadRequest

from magnumclient.client import Client as MagnumClient
from magnumclient.exceptions import HTTPBadRequest as MagnumBadRequest

from octaviaclient.api.v2.octavia import OctaviaAPI as OctaviaClient
from octaviaclient.api.v2.octavia import OctaviaClientException


def getLogger(name):
    logger = logging.getLogger(name)
    logger.setLevel('DEBUG')
    return logger

LOG = getLogger(__name__)

_MISSING = type('MissingValue', tuple(), dict())()


class BadQuota(Exception):
    pass


class QuotaUpdater(object):
    """Base class for quota updaters"""

    def __init__(self, client, project_id):
        self._client = client
        self._project_id = project_id
        self._prev = None

    def update(self, quotas):
        """Update quota values"""

        self._prev = self._update(quotas)

    def rollback(self, ):
        if self._prev is None:
            return
        self.update(self._prev)
        self._prev = None

    def _update(self, quotas):
        raise NotImplementedError()


class CinderQuotaUpdater(QuotaUpdater):
    def _update(self, quotas):
        """Update volumes quotas"""

        current_quotas = {
            key: value for key, value in
            self._client.quotas.get(self._project_id).to_dict().items()
            if key.startswith('gigabytes_')
        }
        new_quotas = {key: 0 for key in current_quotas.keys()}

        total = 0
        for vt in quotas.keys():
            value = quotas[vt]
            if total == -1 or value == -1:
                total = -1
            else:
                total += value
            new_quotas[vt] = value
        new_quotas['gigabytes'] = total
        try:
            self._client.quotas.update(self._project_id, **new_quotas)
            return current_quotas
        except CinderBadRequest:
            raise BadQuota('Current storage usage is higher than new limit.')


class NovaQuotaUpdater(QuotaUpdater):
    def _update(self, quotas):
        """Update cores and ram quotas"""

        current_quotas = {
            key: value for key, value in
            self._client.quotas.get(self._project_id).to_dict().items()
            if key in {'cores', 'ram'}
        }

        try:
            self._client.quotas.update(self._project_id, **quotas)
            return current_quotas
        except NovaBadRequest:
            raise BadQuota('Current CPU and RAM usage is higher '
                           'than new limits.')


class NeutronQuotaUpdater(QuotaUpdater):
    def _update(self, quotas):
        """Update floating ip quotas"""

        quota_and_usage = self._client.show_quota_details(self._project_id)['quota']
        current_quotas = {
            key: value['limit'] for key, value in quota_and_usage.items()
            if key in {'floatingip'}
        }

        try:
            if (quotas.get('floatingip', -1) >= 0 and
                    (quota_and_usage.get('floatingip', {}).get('used', 0) >
                     quotas['floatingip'])):
                raise NeutronBadRequest()
            self._client.update_quota(self._project_id,
                                      body=dict(quota=quotas))
            return current_quotas
        except NeutronBadRequest:
            raise BadQuota('Current amount of Floating IPs is higher '
                           'than new limits.')


class MagnumQuotaUpdater(QuotaUpdater):
    def _update(self, quotas):
        """Update k8saas clusters quota"""

        if not self._client:
            return

        quota_and_usage = self._client.quotas.get(
            self._project_id, 'Cluster')
        current_quotas = {'hard_limit': quota_and_usage.hard_limit}

        try:
            if (quotas.get('hard_limit', -1) >= 0 and
                    (quota_and_usage.in_use > quotas['hard_limit'])):
                raise MagnumBadRequest()
            if not hasattr(quota_and_usage, 'created_at'):
                self._client.quotas.create(project_id=self._project_id,
                                           resource='Cluster',
                                           **quotas)
            else:
                self._client.quotas.update(self._project_id, 'Cluster', quotas)
            return current_quotas
        except MagnumBadRequest:
            raise BadQuota('Current kubernetes cluster amount is higher '
                           'than new limits.')


class OctaviaQuotaUpdater(QuotaUpdater):
    def _update(self, quotas):
        """Update loadbalancers quota"""

        if not self._client:
            return

        quota_and_usage = self._client.quota_show(self._project_id)
        current_quotas = {
            key: value for key, value in quota_and_usage.items()
            if key in {'load_balancer'}
        }

        try:
            if (quotas.get('load_balancer', -1) >= 0 and
                    (quota_and_usage.get('in_use_load_balancer') or 0) >
                    quotas['load_balancer']):
                raise OctaviaClientException(code=400)
            self._client.quota_set(self._project_id, json=dict(quota=quotas))
            return current_quotas
        except OctaviaClientException as e:
            if e.code != 400:
                raise
            raise BadQuota('Current amount of LoadBalancers is higher '
                           'than new limits.')


class ConnectorConfig(Config):
    """Extention of CloudBlue connect config model"""

    @staticmethod
    def _read_config_value(config, key, default=_MISSING):
        if default is _MISSING:
            if key not in config:
                raise ValueError(
                    '"{}" not found in the config file'.format(key))
        val = config.get(key, default)
        if isinstance(val, dict):
            return val
        return val.encode('utf-8') if not isinstance(val, str) else val

    def __init__(self, **kwargs):
        filename = kwargs.get('file')
        if filename and not os.path.exists(filename):
            LOG.error('Configuration file "%s" not found.', filename)
            sys.exit(1)
        super(ConnectorConfig, self).__init__(**kwargs)

        # read addintional infrastructure parameters
        if filename:
            with open(filename) as config_file:
                config = json.loads(config_file.read())
            self._infra_keystone_endpoint = self._read_config_value(
                config, 'infraKeystoneEndpoint')
            self._infra_user = self._read_config_value(
                config, 'infraUser')
            self._infra_password = self._read_config_value(
                config, 'infraPassword')
            self._infra_project = self._read_config_value(
                config, 'infraProject', 'admin')
            self._infra_domain = self._read_config_value(
                config, 'inrfaDomain', 'Default')
            self._templates = self._read_config_value(
                config, 'templates', {})

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


class ConnectorMixin(object):
    def _log_exception(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception:
                LOG.exception('XXX')
        return wrapper

    def _once(f):
        """Cache result of a function first call"""
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            rv = getattr(f, 'rv', _MISSING)
            if rv is _MISSING:
                f.rv = f(*args, **kwargs)
            return f.rv
        return wrapper

    def _memoize(f):
        """Cache result of a function call with parameters"""
        f.memory = {}
        @functools.wraps(f)
        def wrapper(self, *args, **kwargs):
            x = None
            try:
                x = tuple(list(args) + [])
            except TypeError:
                LOG.exception('XXX')
            rv = f.memory.get(x, _MISSING)
            if rv is _MISSING:
                rv = f(self, *args, **kwargs)
                f.memory[x] = rv
            return rv
        return wrapper

    @_memoize
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
    @_once
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
    @_once
    def keystone_client(self):
        """Create KeystoneClient object using KeystoneSession"""

        c = Config.get_instance()
        return KeystoneClient(
            session=self.keystone_session,
            endpoint_override=c.infra_keystone_endpoint,
            connect_retries=2,
        )

    @property
    @_once
    def cinder_client(self):
        return CinderClient(
            version='3.45',
            session=self.keystone_session,
            connect_retries=2,
        )

    @property
    @_once
    def gnocchi_client(self):
        return GnocchiClient(
            version='1',
            session=self.keystone_session,
            # connect_retries=2,
        )

    @property
    @_once
    def nova_client(self):
        return NovaClient(
            version='2.60',
            session=self.keystone_session,
            connect_retries=2,
        )

    @property
    @_once
    def neutron_client(self):
        return NeutronClient(
            session=self.keystone_session,
            connect_retries=2,
        )

    @property
    @_once
    def octavia_client(self):
        try:
            endpoint = self.keystone_session.get_endpoint(
                service_type='load-balancer', interface='public')
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
    @_once
    def magnum_client(self):
        try:
            endpoint = self.keystone_session.get_endpoint(
                service_type='container-infra', interface='public')
        except KeystoneEndpointNotFound:
            endpoint = None

        if endpoint is None:
            return endpoint

        return MagnumClient(
            version='1', api_version='1.8', interface='public',
            session=self.keystone_session,
            connect_retries=2,
        )

    @_memoize
    def find_role(self, name):
        """Find user role by name"""

        return self.keystone_client.roles.find(name=name)

    @_log_exception
    def create_or_update_domain(self, name, description=None, enabled=True,
                                domain_id=None):
        domain = None
        if domain_id:
            try:
                domain = self.keystone_client.domains.get(domain_id)
            except KeystoneNotFound:
                # project was removed
                pass
        if domain is None:
            domains = self.keystone_client.domains.list(name=name)
            domain = domains[0] if domains else None
        if domain is None:
            try:
                return self.keystone_client.domains.create(
                    name, description=description, enabled=enabled)
            except KeystoneConflict:
                # race protection
                domains = self.keystone_client.domains.list(name=name)
                domain = domains[0] if domains else None
        return self.keystone_client.domains.update(
            domain, name=name, description=description, enabled=enabled)

    def create_project(self, name, domain, description=None,
                       enabled=True, project_id=None):
        if project_id:
            try:
                return self.keystone_client.projects.get(project_id)
            except KeystoneNotFound:
                # project was removed
                return
        try:
            report_time = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0)
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
            LOG.exception('Something wrong with the requested '
                          'name or password')


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

    def suspend_project(self, request, domain_id, project_id, user_id):
        if project_id:
            try:
                report_time = datetime.utcnow().replace(microsecond=0)
                params = {}
                if request.asset.status != 'suspended':
                    params['stop_usage_report_time'] = report_time.isoformat()
                self.keystone_client.projects.update(
                    project_id, enabled=False,
                    **params)
            except KeystoneNotFound:
                pass

    @_log_exception
    def configure_storage_quotas(self, project_id, quotas):
        current_quotas = self.cinder_client.quotas.get(project_id)
        gigabytes_quotas = {key:0 for key in current_quotas.to_dict().keys()
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

    @_log_exception
    def configure_compute_quotas(self, project_id, quotas):
        self.nova_client.quotas.update(project_id, **quotas)

    @_log_exception
    def configure_network_quotas(self, project_id, quotas):
        self.neutron_client.update_quota(project_id, body=dict(quota=quotas))

    @_log_exception
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
        return (last_report_time, confirmed) if last_report_time else \
            (datetime.utcnow().replace(
                hour=0, minute=0, second=0,
                microsecond=0), None)

    def _get_report_time(self, request, project, field):
        project_dict = project.to_dict()
        time_str = project_dict.get(field)
        report_time = None
        try:
            report_time = \
                dateutil.parser.parse(time_str) if time_str else None
        except Exception:
            LOG.exception('%s-%s: unable to parse "%s"',
                          request.id, project.id, time_str)
        return report_time

    def get_stop_report_time(self, request, project):
        return self._get_report_time(
            request, project, 'stop_usage_report_time')

    def get_start_report_time(self, request, project):
        return self._get_report_time(
            request, project, 'start_usage_report_time')
