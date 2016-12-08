from collections import defaultdict
from itertools import chain

from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.db.models import Count, Q
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from credit.models import Credit
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import SenderProfile, PrisonerProfile
from transaction.tests.utils import generate_transactions


class SecurityViewTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, _, self.security_staff = make_test_users()
        load_random_prisoner_locations()
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles')

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_url(self, *args, **kwargs):
        return reverse('senderprofile-list')

    def _get_authorised_user(self):
        return self.security_staff[0]

    def _get_list(self, user, **filters):
        url = self._get_url()

        if 'limit' not in filters:
            filters['limit'] = 1000
        response = self.client.get(
            url, filters, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        return response.data


class SenderProfileListTestCase(SecurityViewTestCase):

    def _get_url(self, *args, **kwargs):
        return reverse('senderprofile-list')

    def test_filter_by_prisoner_count(self):
        data = self._get_list(self._get_authorised_user(), prisoner_count__gte=3)['results']
        bank_prisoner_counts = Credit.objects.filter(transaction__isnull=False).values(
                'transaction__sender_name',
                'transaction__sender_sort_code',
                'transaction__sender_account_number',
                'transaction__sender_roll_number',
            ).order_by(
                'transaction__sender_name',
                'transaction__sender_sort_code',
                'transaction__sender_account_number',
                'transaction__sender_roll_number'
            ).annotate(prisoner_count=Count('prisoner_number', distinct=True)
        )
        bank_prisoner_counts = bank_prisoner_counts.filter(prisoner_count__gte=3)

        card_prisoner_counts = Credit.objects.filter(payment__isnull=False).values(
                'payment__card_expiry_date',
                'payment__card_number_last_digits',
            ).order_by(
                'payment__card_expiry_date',
                'payment__card_number_last_digits'
            ).annotate(prisoner_count=Count('prisoner_number', distinct=True)
        )
        card_prisoner_counts = card_prisoner_counts.filter(prisoner_count__gte=3)

        self.assertEqual(
            len(bank_prisoner_counts) + len(card_prisoner_counts), len(data)
        )

    def test_filter_by_prison(self):
        data = self._get_list(self._get_authorised_user(), prison='IXB')['results']

        sender_profiles = SenderProfile.objects.filter(
            prisoners__prisons__nomis_id='IXB'
        ).distinct()

        self.assertEqual(len(data), sender_profiles.count())
        for sender in sender_profiles:
            self.assertTrue(sender.id in [d['id'] for d in data])

    def test_filter_by_multiple_prisons(self):
        data = self._get_list(self._get_authorised_user(), prison=['IXB', 'INP'])['results']

        sender_profiles = SenderProfile.objects.filter(
            Q(prisoners__prisons__nomis_id='IXB') |
            Q(prisoners__prisons__nomis_id='INP')
        ).distinct()

        self.assertEqual(len(data), sender_profiles.count())
        for sender in sender_profiles:
            self.assertTrue(sender.id in [d['id'] for d in data])


class PrisonerProfileListTestCase(SecurityViewTestCase):

    def _get_url(self, *args, **kwargs):
        return reverse('prisonerprofile-list')

    def test_filter_by_sender_count(self):
        data = self._get_list(self._get_authorised_user(), sender_count__gte=3)['results']
        bank_pairs = (
            Credit.objects.filter(transaction__isnull=False, prisoner_number__isnull=False).values(
                'prisoner_number',
                'transaction__sender_name',
                'transaction__sender_sort_code',
                'transaction__sender_account_number',
                'transaction__sender_roll_number'
            ).order_by(
                'prisoner_number',
                'transaction__sender_name',
                'transaction__sender_sort_code',
                'transaction__sender_account_number',
                'transaction__sender_roll_number'
            ).distinct()
        )

        card_pairs = (
            Credit.objects.filter(payment__isnull=False, prisoner_number__isnull=False).values(
                'prisoner_number',
                'payment__card_expiry_date',
                'payment__card_number_last_digits'
            ).order_by(
                'prisoner_number',
                'payment__card_expiry_date',
                'payment__card_number_last_digits'
            ).distinct()
        )

        total_counts = defaultdict(int)
        for pair in chain(bank_pairs, card_pairs):
            total_counts[pair['prisoner_number']] += 1

        greater_than_3_count = 0
        for prisoner in total_counts:
            if total_counts[prisoner] >= 3:
                greater_than_3_count += 1

        self.assertEqual(
            greater_than_3_count, len(data)
        )
