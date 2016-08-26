import base64
from datetime import datetime, time, timedelta
import logging
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone
import requests

from transaction.constants import TRANSACTION_CATEGORY, TRANSACTION_SOURCE, TRANSACTION_STATUS
from transaction.models import Transaction

logger = logging.getLogger('mtp')


class BaseUpdater:
    resource = NotImplemented
    period = NotImplemented

    def __init__(self, timestamp=None, **kwargs):
        if timestamp:
            self.timestamp = timestamp
        else:
            self.timestamp = timezone.now()
            if self.period == 'week':
                self.timestamp = timezone.make_aware(
                    datetime.combine(self.timestamp, time.min) -
                    timedelta(days=self.timestamp.weekday(), weeks=1)
                )
        self.data = dict(**kwargs)

    def _headers(self):
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % settings.PERFORMANCE_PLATFORM_API_TOKEN
        }

    def _category(self):
        return self.resource

    def _count(self):
        raise NotImplementedError

    def run(self):
        govuk_timestamp = self.timestamp.replace(tzinfo=timezone.utc).isoformat()
        self.data.update(
            service='money to prisoners',
            period=self.period,
            _timestamp=govuk_timestamp,
            _id=base64.b64encode(bytes(
                '%s.%s.money to prisoners.%s'
                % (govuk_timestamp, self.period, self._category()),
                'utf-8'
            )).decode('utf-8'),
            count=self._count()
        )
        response = requests.post(
            urljoin(settings.PERFORMANCE_PLATFORM_API_URL, self.resource),
            headers=self._headers(),
            json=[self.data]
        )
        if response.status_code != 200:
            logger.error(
                'Performance platform update failed for %s: %s'
                % (self.resource, response.json())
            )


class CompletionRateUpdater(BaseUpdater):
    resource = 'completion-rate'
    period = 'week'
    stage = NotImplemented

    def __init__(self, timestamp=None, **kwargs):
        super().__init__(timestamp=timestamp, stage=self.stage, **kwargs)

    def _category(self):
        return self.stage

    def _get_queryset(self):
        end_date = self.timestamp + timedelta(days=7)
        return Transaction.objects.filter(
            received_at__date__gte=self.timestamp,
            received_at__date__lt=end_date,
            category=TRANSACTION_CATEGORY.CREDIT,
            source=TRANSACTION_SOURCE.BANK_TRANSFER
        )


class TotalCompletionRateUpdater(CompletionRateUpdater):
    stage = 'total'

    def _count(self):
        return self._get_queryset().count()


class ValidCompletionRateUpdater(CompletionRateUpdater):
    stage = 'valid'

    def _count(self):
        return self._get_queryset().filter(
            Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITABLE]
        ).count()


class InvalidCompletionRateUpdater(CompletionRateUpdater):
    stage = 'invalid'

    def _count(self):
        queryset = self._get_queryset()
        return queryset.filter(
            ~Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITABLE]
        ).count()

registry = {}
registry['completion-rate'] = [
    TotalCompletionRateUpdater,
    ValidCompletionRateUpdater,
    InvalidCompletionRateUpdater
]
