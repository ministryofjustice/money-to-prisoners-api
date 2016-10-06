from datetime import datetime, timedelta
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils.timezone import utc

from core.tests.utils import make_test_users
from credit.models import Credit
from payment.models import Payment
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations


class AbandonedPaymentClearingTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']
    payment_count = 100

    def setUp(self):
        make_test_users(1)
        load_random_prisoner_locations(1)
        self.payments = generate_payments(self.payment_count, days_of_history=10)

    @mock.patch('django.utils.timezone.now')
    def test_clearing_abandoned_payments(self, mocked_now):
        now = datetime(2016, 10, 5, 12, tzinfo=utc)
        mocked_now.return_value = now
        abandoned_count = Payment.objects.abandoned(now - timedelta(days=2)).count()
        call_command('clear_abandoned_payments', age=2, verbosity=0)
        expected_total_payment_count = self.payment_count - abandoned_count
        self.assertEqual(expected_total_payment_count, Payment.objects.all().count())
        self.assertEqual(expected_total_payment_count, Credit.objects_all.all().count())

    @mock.patch('django.utils.timezone.now')
    def test_clearing_abandoned_payments_does_nothing_if_none_exist(self, mocked_now):
        now = datetime(2016, 10, 5, 12, tzinfo=utc)
        mocked_now.return_value = now
        abandoned_count = Payment.objects.abandoned(now - timedelta(days=2)).count()
        call_command('clear_abandoned_payments', age=2, verbosity=0)
        expected_total_payment_count = self.payment_count - abandoned_count
        self.assertEqual(expected_total_payment_count, Payment.objects.all().count())
        self.assertEqual(expected_total_payment_count, Credit.objects_all.all().count())
        abandoned_count = Payment.objects.abandoned(now - timedelta(days=2)).count()
        self.assertEqual(abandoned_count, 0)
        call_command('clear_abandoned_payments', age=2, verbosity=0)
        self.assertEqual(expected_total_payment_count, Payment.objects.all().count())
        self.assertEqual(expected_total_payment_count, Credit.objects_all.all().count())

    def test_clearing_with_invalid_age(self):
        with self.assertRaises(CommandError):
            call_command('clear_abandoned_payments', age=0, verbosity=0)
        self.assertEqual(self.payment_count, Payment.objects.all().count())
