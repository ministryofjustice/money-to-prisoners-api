import datetime

from django.utils import timezone
from model_mommy import mommy
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from credit.models import Credit, PrivateEstateBatch
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.tests.utils import generate_payments
from prison.models import Prison, PrisonBankAccount
from prison.tests.utils import load_random_prisoner_locations
from transaction.tests.utils import generate_transactions


class PrivateEstateBatchTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = [
        'initial_groups.json',
        'initial_types.json',
        'test_prisons.json',
    ]

    def setUp(self):
        super().setUp()

        self.private_prison = mommy.make(Prison, name='Private', private_estate=True)
        mommy.make(PrisonBankAccount, prison=self.private_prison)

        test_users = make_test_users(clerks_per_prison=2)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        load_random_prisoner_locations()

        transaction_credits = [
            t.credit for t in generate_transactions(transaction_batch=10, days_of_history=3)
            if t.credit
        ]
        payment_credits = [
            p.credit for p in generate_payments(payment_batch=10, days_of_history=3)
            if p.credit and p.credit.resolution != 'initial'
        ]
        self.credits = transaction_credits + payment_credits
        self.prisons = Prison.objects.all()

    def test_reconciliation_creates_batch(self):
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        date = Credit.objects.earliest().received_at.replace(hour=0, minute=0, second=0, microsecond=0)
        while date < today:
            end_of_date = date + datetime.timedelta(days=1)
            PrivateEstateBatch.objects.create_batches(date, end_of_date)
            date = end_of_date

        for batch in PrivateEstateBatch.objects.all():
            self.assertTrue(all(
                map(lambda credit: credit.prison.private_estate, batch.credit_set.all())
            ))
            self.assertTrue(all(
                map(lambda credit: credit.credit_pending or credit.credited, batch.credit_set.all())
            ))
            self.assertTrue(all(
                map(lambda credit: credit.received_at.date() == batch.date, batch.credit_set.all())
            ))

        credits_not_in_batches = [
            credit
            for credit in Credit.objects.filter(private_estate_batch__isnull=True)
            if credit.credit_pending or credit.credited
        ]
        self.assertFalse(any(
            map(lambda credit: credit.prison and credit.prison.private_estate, credits_not_in_batches)
        ))
