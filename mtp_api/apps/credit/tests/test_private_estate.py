import datetime

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from model_mommy import mommy
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from credit.constants import CREDIT_RESOLUTION
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
        self.private_bank_account = mommy.make(PrisonBankAccount, prison=self.private_prison)

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

        self.latest_date = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        date = Credit.objects.earliest().received_at.replace(hour=0, minute=0, second=0, microsecond=0)
        while date < self.latest_date:
            end_of_date = date + datetime.timedelta(days=1)
            PrivateEstateBatch.objects.create_batches(date, end_of_date)
            date = end_of_date

    def test_reconciliation_creates_batch(self):
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
            if (credit.credit_pending or credit.credited) and credit.received_at < self.latest_date
        ]
        self.assertFalse(any(
            map(lambda credit: credit.prison and credit.prison.private_estate, credits_not_in_batches)
        ))

    def test_bank_admin_can_get_batches(self):
        date_with_batch = Credit.objects.credited().filter(prison__private_estate=True).earliest().received_at.date()
        expected_batch = PrivateEstateBatch.objects.filter(date=date_with_batch).first()

        user = self.bank_admins[0]
        url = reverse('privateestatebatch-list')
        response = self.client.get(
            url, {'date': date_with_batch}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        batches = response.data['results']
        self.assertEqual(len(batches), 1)
        batch = batches[0]
        self.assertEqual(batch['date'], date_with_batch.isoformat())
        self.assertEqual(batch['prison'], self.private_prison.nomis_id)
        self.assertEqual(batch['total_amount'], expected_batch.total_amount)
        self.assertEqual(batch['bank_account']['postcode'], self.private_bank_account.postcode)
        self.assertEqual(batch['bank_account']['account_number'], self.private_bank_account.account_number)

    def test_others_cannot_get_batches(self):
        date_with_batch = Credit.objects.credited().filter(prison__private_estate=True).earliest().received_at.date()

        user = self.prison_clerks[0]
        url = reverse('privateestatebatch-list')
        response = self.client.get(
            url, {'date': date_with_batch}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bank_admin_can_list_credits_in_batch(self):
        date_with_batch = Credit.objects.credited().filter(prison__private_estate=True).earliest().received_at.date()
        expected_batch = PrivateEstateBatch.objects.filter(date=date_with_batch).first()

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
            parse_datetime(credit['received_at']).date() == date_with_batch
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
        date_with_batch = Credit.objects.credited().filter(prison__private_estate=True).earliest().received_at.date()
        expected_batch = PrivateEstateBatch.objects.filter(date=date_with_batch).first()

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
        date_with_batch = Credit.objects.credited().filter(prison__private_estate=True).earliest().received_at.date()
        expected_batch = PrivateEstateBatch.objects.filter(date=date_with_batch).first()
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
        date_with_batch = Credit.objects.credited().filter(prison__private_estate=True).earliest().received_at.date()
        expected_batch = PrivateEstateBatch.objects.filter(date=date_with_batch).first()

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
        date_with_batch = Credit.objects.credited().filter(prison__private_estate=True).earliest().received_at.date()
        expected_batch = PrivateEstateBatch.objects.filter(date=date_with_batch).first()

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
