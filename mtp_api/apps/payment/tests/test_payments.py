from datetime import datetime, time, timedelta

from django.conf import settings
from django.test import TestCase
from django.utils.timezone import utc

from core.tests.utils import make_test_users
from payment.constants import PAYMENT_STATUS
from payment.models import Batch, Payment
from payment.tests.utils import generate_payments, latest_payment_date
from prison.tests.utils import load_random_prisoner_locations


def get_worldpay_cutoff(date):
    return datetime.combine(date, time(0, 0, 0, tzinfo=utc))


class ReconcilePaymentsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users()
        load_random_prisoner_locations()

    def _get_date_bounds(self):
        start_date = get_worldpay_cutoff(latest_payment_date())
        end_date = get_worldpay_cutoff(latest_payment_date() + timedelta(days=1))
        return start_date, end_date

    def test_batch_created_by_reconciliation(self):
        generate_payments(100)
        Batch.objects.all().delete()

        start_date, end_date = self._get_date_bounds()

        initial_batch_count = Batch.objects.all().count()
        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=start_date,
            credit__received_at__lt=end_date
        ):
            self.assertIsNone(payment.batch)
            self.assertIsNone(payment.ref_code)

        Payment.objects.reconcile(start_date, end_date, None)

        self.assertEqual(Batch.objects.all().count(), initial_batch_count + 1)
        new_batch = Batch.objects.latest()
        self.assertEqual(new_batch.date, latest_payment_date().date())

        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=start_date,
            credit__received_at__lt=end_date
        ):
            self.assertEqual(payment.batch, new_batch)
            self.assertEqual(payment.ref_code, str(settings.CARD_REF_CODE_BASE))

        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__lt=start_date,
        ):
            self.assertNotEqual(payment.batch, new_batch)

        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=end_date,
        ):
            self.assertNotEqual(payment.batch, new_batch)
            self.assertFalse(payment.credit.reconciled)

    def test_ref_code_increments(self):
        generate_payments(100)
        Batch.objects.all().delete()

        start_date, end_date = self._get_date_bounds()
        previous_date = start_date - timedelta(days=1)

        Batch(date=previous_date.date() - timedelta(days=1), ref_code='800002').save()
        Batch(date=previous_date.date() - timedelta(days=2), ref_code='800001').save()

        Payment.objects.reconcile(start_date, end_date, None)
        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=start_date,
            credit__received_at__lt=end_date
        ):
            self.assertEqual(payment.ref_code, '800003')

    def test_no_new_batch_created_if_no_payments(self):
        start_date, end_date = self._get_date_bounds()

        initial_batch_count = Batch.objects.all().count()
        Payment.objects.reconcile(start_date, end_date, None)
        self.assertEqual(Batch.objects.all().count(), initial_batch_count)
