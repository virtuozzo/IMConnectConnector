# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from cinderclient.exceptions import BadRequest as CinderBadRequest
from magnumclient.exceptions import HTTPBadRequest as MagnumBadRequest
from neutronclient.common.exceptions import BadRequest as NeutronBadRequest
from novaclient.exceptions import BadRequest as NovaBadRequest
from octaviaclient.api.v2.octavia import OctaviaClientException


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
            raise BadQuota('Current CPU and RAM usage is higher than new limits.')


class NeutronQuotaUpdater(QuotaUpdater):
    def _update(self, quotas):
        """Update floating ip quotas"""

        quota_and_usage = self._client.show_quota_details(self._project_id)['quota']
        current_quotas = {
            key: value['limit'] for key, value in quota_and_usage.items()
            if key in {'floatingip'}
        }

        try:
            if (quotas.get('floatingip', -1) >= 0
                    and (quota_and_usage.get('floatingip', {}).get('used', 0) > quotas['floatingip'])):
                raise NeutronBadRequest()
            self._client.update_quota(self._project_id, body=dict(quota=quotas))
            return current_quotas
        except NeutronBadRequest:
            raise BadQuota('Current amount of Floating IPs is higher than new limits.')


class MagnumQuotaUpdater(QuotaUpdater):
    def _update(self, quotas):
        """Update k8saas clusters quota"""

        if not self._client:
            return

        quota_and_usage = self._client.quotas.get(self._project_id, 'Cluster')
        current_quotas = {'hard_limit': quota_and_usage.hard_limit}

        try:
            if quotas.get('hard_limit', -1) >= 0 and (quota_and_usage.in_use > quotas['hard_limit']):
                raise MagnumBadRequest()
            if not hasattr(quota_and_usage, 'created_at'):
                self._client.quotas.create(project_id=self._project_id, resource='Cluster', **quotas)
            else:
                self._client.quotas.update(self._project_id, 'Cluster', quotas)
            return current_quotas
        except MagnumBadRequest:
            raise BadQuota('Current kubernetes cluster amount is higher than new limits.')


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
            if (quotas.get('load_balancer', -1) >= 0
                    and (quota_and_usage.get('in_use_load_balancer') or 0) > quotas['load_balancer']):
                raise OctaviaClientException(code=400)
            self._client.quota_set(self._project_id, json=dict(quota=quotas))
            return current_quotas
        except OctaviaClientException as e:
            if e.code != 400:
                raise
            raise BadQuota('Current amount of LoadBalancers is higher than new limits.')
