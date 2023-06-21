import base64
from datetime import date, datetime, timedelta
from unittest import mock

from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from core.tests.utils import make_test_users
from performance import updaters
from performance.models import DigitalTakeup
from prison.models import Prison
from prison.tests.utils import load_random_prisoner_locations
from transaction.constants import TransactionStatus, TransactionCategory, TransactionSource
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions


class CompletionRateTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users()
        load_random_prisoner_locations()
        generate_transactions(transaction_batch=100, days_of_history=21)

    @mock.patch('performance.updaters.timezone.now')
    def test_last_week_timestamp(self, mock_now):
        mock_now.return_value = datetime(2016, 8, 22, 12, 54, 53, tzinfo=timezone.utc)

        updater = updaters.TotalCompletionRateUpdater()
        self.assertEqual(
            updater.timestamp,
            timezone.make_aware(datetime(2016, 8, 15, 0, 0, 0))
        )

    def _get_db_count(self, timestamp, *q_filters, **kw_filters):
        today = timestamp or datetime.now()
        last_week_start = today - timedelta(days=today.weekday(), weeks=1)
        return Transaction.objects.filter(
            *q_filters,
            received_at__date__gte=last_week_start.date(),
            received_at__date__lt=(last_week_start.date() + timedelta(days=7)),
            category=TransactionCategory.credit,
            source=TransactionSource.bank_transfer.value,
            **kw_filters
        ).count()

    def _test_count_correct(self, update_count, *q_filters, **kw_filters):
        db_count = self._get_db_count(None, *q_filters, **kw_filters)
        self.assertEqual(update_count, db_count)

    def test_total_credits_correct(self):
        updater = updaters.TotalCompletionRateUpdater()
        self._test_count_correct(
            updater._count()
        )

    def test_valid_credits_correct(self):
        updater = updaters.ValidCompletionRateUpdater()
        self._test_count_correct(
            updater._count(),
            Transaction.STATUS_LOOKUP[TransactionStatus.creditable.value]
        )

    def test_invalid_credits_correct(self):
        updater = updaters.InvalidCompletionRateUpdater()
        self._test_count_correct(
            updater._count(),
            ~Transaction.STATUS_LOOKUP[TransactionStatus.creditable.value]
        )

    @mock.patch('performance.updaters.timezone.now')
    @mock.patch('performance.updaters.requests')
    def test_run(self, mock_requests, mock_now):
        timestamp = datetime(2016, 8, 22, 12, 54, 53, tzinfo=timezone.utc)
        mock_now.return_value = timestamp
        mock_requests.post.return_value = mock.MagicMock()
        mock_requests.post.return_value.status_code = 200

        updater = updaters.TotalCompletionRateUpdater()
        updater.run()

        mock_requests.post.assert_called_once_with(
            'http://localhost/completion-rate',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': 'Bearer not_a_token'
            },
            json=[{
                'service': 'money to prisoners',
                'period': 'week',
                'stage': 'total',
                '_timestamp': '2016-08-15T00:00:00+00:00',
                '_id': base64.b64encode(bytes(
                    '2016-08-15T00:00:00+00:00.week.money to prisoners.completion-rate.total',
                    'utf-8')
                ).decode('utf-8'),
                'count': self._get_db_count(timestamp)
            }]
        )


class TransactionsByChannelTypeTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.data_date = date(2016, 8, 21)
        self.now = datetime(2016, 8, 22, 12, 54, 53, tzinfo=timezone.utc)
        DigitalTakeup(
            date=self.data_date, prison=Prison.objects.all()[0], credits_by_post=3, credits_by_mtp=5
        ).save()
        DigitalTakeup(
            date=self.data_date, prison=Prison.objects.all()[1], credits_by_post=7, credits_by_mtp=11
        ).save()

    def _get_db_count(self, timestamp):
        today = timestamp.date() if timestamp else self.data_date
        return DigitalTakeup.objects.filter(
            date__gte=today,
            date__lt=today + timedelta(days=1),
        )

    def _test_count_correct(self, update_count):
        db_count = self._get_db_count(None).aggregate(
            sum_credits_by_post=Sum('credits_by_post')
        )['sum_credits_by_post']
        self.assertEqual(update_count, db_count)

    @mock.patch('performance.updaters.timezone.now')
    def test_digital_transactions_correct(self, mock_now):
        mock_now.return_value = self.now
        updater = updaters.TransactionsByDigitalUpdater()
        db_count = self._get_db_count(None).aggregate(
            sum_credits_by_mtp=Sum('credits_by_mtp')
        )['sum_credits_by_mtp']
        self.assertEqual(updater._count(), db_count)

    @mock.patch('performance.updaters.timezone.now')
    def test_post_transactions_correct(self, mock_now):
        mock_now.return_value = self.now
        updater = updaters.TransactionsByPostUpdater()
        db_count = self._get_db_count(None).aggregate(
            sum_credits_by_post=Sum('credits_by_post')
        )['sum_credits_by_post']
        self.assertEqual(updater._count(), db_count)

    @mock.patch('performance.updaters.timezone.now')
    @mock.patch('performance.updaters.requests')
    def test_run(self, mock_requests, mock_now):
        mock_now.return_value = self.now
        mock_requests.post.return_value = mock.MagicMock()
        mock_requests.post.return_value.status_code = 200

        updater = updaters.TransactionsByPostUpdater()
        updater.run()

        mock_requests.post.assert_called_once_with(
            'http://localhost/transactions-by-channel-type',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': 'Bearer also_not_a_token'
            },
            json=[{
                'service': 'money to prisoners',
                'period': 'day',
                'channel': 'post',
                '_timestamp': '2016-08-21T00:00:00+00:00',
                '_id': base64.b64encode(bytes(
                    '2016-08-21T00:00:00+00:00.day.money to prisoners.transactions-by-channel-type.post',
                    'utf-8')
                ).decode('utf-8'),
                'count': self._get_db_count(None).aggregate(
                    sum_credits_by_post=Sum('credits_by_post')
                )['sum_credits_by_post']
            }]
        )
