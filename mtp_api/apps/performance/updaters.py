"""
NB: GOV.UK have retired the performance platform
"""

import base64
from datetime import datetime, time, timedelta
import logging
from urllib.parse import urljoin

from django.conf import settings
from django.db import models
from django.utils import timezone
import requests

from performance.models import DigitalTakeup
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
            elif self.period == 'day':
                self.timestamp = timezone.make_aware(
                    datetime.combine(self.timestamp, time.min) -
                    timedelta(days=1)
                )

        self.data = dict(**kwargs)

    def _headers(self):
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % settings.PERFORMANCE_PLATFORM_API_TOKENS[self.resource]
        }

    def _category(self):
        return self.resource

    def _count(self):
        raise NotImplementedError

    def _skip(self):
        return False

    def run(self):
        if self._skip():
            logger.warning('Performance platform update skipped', {'resource': self.resource})
            return
        govuk_timestamp = self.timestamp.replace(tzinfo=timezone.utc).isoformat()
        self.data.update(
            service='money to prisoners',
            period=self.period,
            _timestamp=govuk_timestamp,
            _id=base64.b64encode(bytes(
                '%s.%s.money to prisoners.%s.%s'
                % (govuk_timestamp, self.period, self.resource, self._category()),
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
                'Performance platform update failed',
                {'resource': self.resource, 'response_payload': response.json()}
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
            received_at__date__gte=self.timestamp.date(),
            received_at__date__lt=end_date.date(),
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


class TransactionsByChannelTypeUpdater(BaseUpdater):
    resource = 'transactions-by-channel-type'
    period = 'day'
    channel = NotImplemented

    def __init__(self, timestamp=None, **kwargs):
        super().__init__(timestamp=timestamp, channel=self.channel, **kwargs)

    def _category(self):
        return self.channel

    def _get_queryset(self):
        end_date = self.timestamp + timedelta(days=1)
        return DigitalTakeup.objects.filter(
            date__gte=self.timestamp.date(),
            date__lt=end_date.date(),
        )

    def _skip(self):
        return self._get_queryset().count() == 0


class TransactionsByDigitalUpdater(TransactionsByChannelTypeUpdater):
    channel = 'digital'

    def _count(self):
        queryset = self._get_queryset()
        return queryset.aggregate(
            sum_credits_by_mtp=models.Sum('credits_by_mtp')
        )['sum_credits_by_mtp']


class TransactionsByPostUpdater(TransactionsByChannelTypeUpdater):
    channel = 'post'

    def _count(self):
        queryset = self._get_queryset()
        return queryset.aggregate(
            sum_credits_by_post=models.Sum('credits_by_post')
        )['sum_credits_by_post']


registry = {
    'completion-rate': [
        TotalCompletionRateUpdater,
        ValidCompletionRateUpdater,
        InvalidCompletionRateUpdater
    ],
    'transactions-by-channel-type': [
        TransactionsByDigitalUpdater,
        TransactionsByPostUpdater
    ],
}
