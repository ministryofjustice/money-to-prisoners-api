import datetime

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from model_bakery import baker
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, FLAKY_TEST_WARNING
from credit.constants import CREDIT_RESOLUTION, CREDIT_STATUS
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

        self.private_prison = baker.make(Prison, name='Private', private_estate=True)
        self.private_bank_account = baker.make(PrisonBankAccount, prison=self.private_prison)

        test_users = make_test_users(clerks_per_prison=2)
        self.prison_clerks = test_users['prison_clerks']
        self.bank_admins = test_users['bank_admins']
        load_random_prisoner_locations()

        transaction_credits = [
            t.credit for t in generate_transactions(transaction_batch=20, days_of_history=4)
            if t.credit
        ]
        payment_credits = [
            p.credit for p in generate_payments(payment_batch=20, days_of_history=4)
            if p.credit and p.credit.resolution != 'initial'
        ]
        self.credits = transaction_credits + payment_credits
        self.prisons = Prison.objects.all()

        creditable = Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED] | Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDIT_PENDING]
        private_estate_credit_set = Credit.objects.filter(prison__private_estate=True).filter(creditable)
        if not private_estate_credit_set.exists():
            public_estate_credits = Credit.objects.filter(prison__private_estate=False).filter(creditable)
            public_estate_credits[public_estate_credits.count() // 2:].update(prison=self.private_prison)

        self.latest_date = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

        date = timezone.localtime(Credit.objects.earliest().received_at)
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        while date < self.latest_date:
            end_of_date = date + datetime.timedelta(days=1)
            PrivateEstateBatch.objects.create_batches(date, end_of_date)
            date = end_of_date

        try:
            earliest = Credit.objects.credited().filter(prison__private_estate=True).earliest()
            self.date_with_batch = timezone.localdate(earliest.received_at)
        except Credit.DoesNotExist:
            self._raise_flaky_test_warning()

    def _raise_flaky_test_warning(self):
        """
        Raise an exception to warn about the flaky nature of this test

        Message includes information about the credits, useful to debug this
        """

        all_credits = Credit.objects.count()
        credited = Credit.objects.credited().count()
        private_estate = Credit.objects.credited().filter(prison__private_estate=True).count()

        raise Exception(
            f'{FLAKY_TEST_WARNING}'
            f'\n\nCredit.objects.count() = {all_credits}'
            f'\nCredit.objects.credited().count() = {credited}'
            f'\nCredit.objects.credited().filter(prison__private_estate=True).count() = {private_estate}'
        )

    def test_reconciliation_creates_batch(self):
        for batch in PrivateEstateBatch.objects.all():
            self.assertTrue(all(
                map(lambda credit: credit.prison.private_estate, batch.credit_set.all())
            ))
            self.assertTrue(all(
                map(lambda credit: credit.credit_pending or credit.credited, batch.credit_set.all())
            ))

            for credit in batch.credit_set.all():
                credit_date = timezone.localdate(credit.received_at)
                self.assertEqual(batch.date, credit_date)

        credits_not_in_batches = [
            credit
            for credit in Credit.objects.filter(private_estate_batch__isnull=True)
            if (credit.credit_pending or credit.credited) and credit.received_at < self.latest_date
        ]
        self.assertFalse(any(
            map(lambda credit: credit.prison and credit.prison.private_estate, credits_not_in_batches)
        ))

    def test_batches_only_contain_private_estate_credits(self):
        creditable = Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED] | Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDIT_PENDING]
        private_estate_credit_ids = set(
            Credit.objects.filter(
                prison__private_estate=True, received_at__lt=self.latest_date,
            ).filter(creditable).values_list('pk', flat=True)
        )
        for batch in PrivateEstateBatch.objects.all():
            for credit_id in batch.credit_set.values_list('pk', flat=True):
                private_estate_credit_ids.remove(credit_id)
        self.assertEqual(len(private_estate_credit_ids), 0)

    def test_bank_admin_can_get_batches(self):
        expected_batch = PrivateEstateBatch.objects.filter(date=self.date_with_batch).first()

        user = self.bank_admins[0]
        url = reverse('privateestatebatch-list')
        response = self.client.get(
            url, {'date': self.date_with_batch}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        batches = response.data['results']
        self.assertEqual(len(batches), 1)
        batch = batches[0]
        self.assertEqual(batch['date'], self.date_with_batch.isoformat())
        self.assertEqual(batch['prison'], self.private_prison.nomis_id)
        self.assertEqual(batch['total_amount'], expected_batch.total_amount)
        self.assertEqual(batch['bank_account']['postcode'], self.private_bank_account.postcode)
        self.assertEqual(batch['bank_account']['account_number'], self.private_bank_account.account_number)

    def test_others_cannot_get_batches(self):
        user = self.prison_clerks[0]
        url = reverse('privateestatebatch-list')
        response = self.client.get(
            url, {'date': self.date_with_batch}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bank_admin_can_list_credits_in_batch(self):
        expected_batch = PrivateEstateBatch.objects.filter(date=self.date_with_batch).first()

        user = self.bank_admins[0]
        url = reverse('privateestatebatch-credit-list', kwargs={
            'batch_ref': '%s/%s' % (
                expected_batch.prison.nomis_id,
                expected_batch.date.isoformat(),
            )
        })
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        credits_list = response.data['results']
        self.assertTrue(all(
            parse_datetime(credit['received_at']).date() == self.date_with_batch
            for credit in credits_list
        ))
        self.assertTrue(all(
            credit['prison'] == self.private_prison.nomis_id
            for credit in credits_list
        ))
        self.assertSetEqual(
            set(credit['id'] for credit in credits_list),
            set(expected_batch.credit_set.values_list('pk', flat=True)),
        )

    def test_others_cannot_list_credits_in_batch(self):
        expected_batch = PrivateEstateBatch.objects.filter(date=self.date_with_batch).first()

        user = self.prison_clerks[0]
        url = reverse('privateestatebatch-credit-list', kwargs={
            'batch_ref': '%s/%s' % (
                expected_batch.prison.nomis_id,
                expected_batch.date.isoformat(),
            )
        })
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_special_bank_admin_can_credit_batch(self):
        expected_batch = PrivateEstateBatch.objects.filter(date=self.date_with_batch).first()
        some_credit = expected_batch.credit_set.first()
        some_credit.resolution = CREDIT_RESOLUTION.PENDING
        some_credit.save()

        user = self.bank_admins[0]
        user.user_permissions.add(Permission.objects.get(codename='change_privateestatebatch'))
        url = reverse('privateestatebatch-detail', kwargs={
            'ref': '%s/%s' % (
                expected_batch.prison.nomis_id,
                expected_batch.date.isoformat(),
            )
        })
        response = self.client.patch(
            url, {'credited': True}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(all(
            credit.credited
            for credit in expected_batch.credit_set.all()
        ))

    def test_normal_bank_admin_cannot_credit_batch(self):
        expected_batch = PrivateEstateBatch.objects.filter(date=self.date_with_batch).first()

        user = self.bank_admins[0]
        url = reverse('privateestatebatch-detail', kwargs={
            'ref': '%s/%s' % (
                expected_batch.prison.nomis_id,
                expected_batch.date.isoformat(),
            )
        })
        response = self.client.patch(
            url, {'credited': True}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_others_cannot_credit_batch(self):
        expected_batch = PrivateEstateBatch.objects.filter(date=self.date_with_batch).first()

        user = self.prison_clerks[0]
        url = reverse('privateestatebatch-detail', kwargs={
            'ref': '%s/%s' % (
                expected_batch.prison.nomis_id,
                expected_batch.date.isoformat(),
            )
        })
        response = self.client.patch(
            url, {'credited': True}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
