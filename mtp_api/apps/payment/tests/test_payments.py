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
    return datetime.combine(date - timedelta(days=1), time(23, 0, tzinfo=utc))


class ReconcilePaymentsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users()
        load_random_prisoner_locations()

    def test_batch_created_by_reconciliation(self):
        generate_payments(100)

        start_date = latest_payment_date().date()
        end_date = start_date + timedelta(days=1)

        initial_batch_count = Batch.objects.all().count()
        for payment in Payment.objects.filter(
                status=PAYMENT_STATUS.TAKEN, credit__received_at__date=start_date):
            self.assertIsNone(payment.batch)
            self.assertIsNone(payment.ref_code)

        Payment.objects.reconcile(start_date, end_date, None)

        self.assertEqual(Batch.objects.all().count(), initial_batch_count + 1)
        new_batch = Batch.objects.latest()
        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=get_worldpay_cutoff(start_date),
            credit__received_at__lt=get_worldpay_cutoff(end_date)
        ):
            self.assertEqual(payment.batch, new_batch)
            self.assertEqual(payment.ref_code, str(settings.CARD_REF_CODE_BASE))

        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__lt=get_worldpay_cutoff(start_date),
        ):
            self.assertNotEqual(payment.batch, new_batch)

        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=get_worldpay_cutoff(end_date),
        ):
            self.assertNotEqual(payment.batch, new_batch)
            self.assertFalse(payment.credit.reconciled)

    def test_ref_code_increments(self):
        generate_payments(100)

        start_date = latest_payment_date().date()
        end_date = start_date + timedelta(days=1)
        previous_date = start_date - timedelta(days=1)

        previous_batch = Batch(date=previous_date,
                               ref_code=str(settings.CARD_REF_CODE_BASE))
        previous_batch.save()

        Payment.objects.reconcile(start_date, end_date, None)
        for payment in Payment.objects.filter(
            status=PAYMENT_STATUS.TAKEN,
            credit__received_at__gte=get_worldpay_cutoff(start_date),
            credit__received_at__lt=get_worldpay_cutoff(end_date)
        ):
            self.assertEqual(payment.ref_code, str(settings.CARD_REF_CODE_BASE + 1))

    def test_no_new_batch_created_if_no_payments(self):
        start_date = latest_payment_date().date()
        end_date = start_date + timedelta(days=1)

        initial_batch_count = Batch.objects.all().count()
        Payment.objects.reconcile(start_date, end_date, None)
        self.assertEqual(Batch.objects.all().count(), initial_batch_count)
