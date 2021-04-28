# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************

from connect import resources
from connect.exceptions import SubmitUsageFile, AcceptUsageFile, SkipRequest

from cloudblue_connector.connector import ConnectorMixin
from cloudblue_connector.core.logger import context_log


class UsageFileAutomation(resources.UsageFileAutomation, ConnectorMixin):
    """Automates workflow of Usage Files."""

    files = []

    @context_log
    def dispatch(self, request):
        try:
            super(UsageFileAutomation, self).dispatch(request)
        except Exception:
            # the error is ignored because we don't want to fail processing
            # of other UsageFiles
            self.logger.exception('Error occurs while dispatching request')
        return 'skip'

    def process_request(self, request):
        """Confirm all UsageFiles that has 'ready' status"""

        # store all processed requests for debug
        self.files.append(request)

        if request.status == 'ready':
            raise SubmitUsageFile()
        elif request.status == 'pending':
            raise AcceptUsageFile('Automatically confirmed')

        raise SkipRequest()

    def filters(self, **kwargs):
        filters = super(UsageFileAutomation, self).filters(status=['ready', 'pending'], **kwargs)
        return filters
