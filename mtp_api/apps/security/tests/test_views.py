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
from mtp_auth.tests.mommy_recipes import create_security_staff_user
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import SenderProfile, PrisonerProfile, SavedSearch, SearchFilter
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

    def _get_list(self, user, path_params=[], **filters):
        url = self._get_url(*path_params)

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
        ).annotate(prisoner_count=Count('prisoner_number', distinct=True))

        bank_prisoner_counts = bank_prisoner_counts.filter(prisoner_count__gte=3)

        card_prisoner_counts = Credit.objects.filter(payment__isnull=False).values(
            'payment__card_expiry_date',
            'payment__card_number_last_digits',
        ).order_by(
            'payment__card_expiry_date',
            'payment__card_number_last_digits'
        ).annotate(prisoner_count=Count('prisoner_number', distinct=True))
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


class SenderCreditListTestCase(SecurityViewTestCase):

    def _get_url(self, *args, **kwargs):
        return reverse('sender-credits-list', args=args)

    def test_list_credits_for_sender(self):
        sender = SenderProfile.objects.last()  # first is anonymous
        data = self._get_list(
            self._get_authorised_user(), path_params=[sender.id]
        )['results']
        self.assertGreater(len(data), 0)

        credits = Credit.objects.filter(sender.credit_filters)
        self.assertEqual(
            len(credits), len(data)
        )
        for credit in credits:
            self.assertTrue(credit.id in [d['id'] for d in data])


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


class PrisonerCreditListTestCase(SecurityViewTestCase):

    def _get_url(self, *args, **kwargs):
        return reverse('prisoner-credits-list', args=args)

    def test_list_credits_for_prisoner(self):
        prisoner = PrisonerProfile.objects.first()
        data = self._get_list(
            self._get_authorised_user(), path_params=[prisoner.id]
        )['results']
        self.assertTrue(len(data) > 0)

        credits = Credit.objects.filter(prisoner.credit_filters)
        self.assertEqual(
            len(credits), len(data)
        )
        for credit in credits:
            self.assertTrue(credit.id in [d['id'] for d in data])


class CreateSavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, _, self.security_staff = make_test_users()

    def _get_url(self, *args, **kwargs):
        return reverse('savedsearch-list')

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]

    def test_create_saved_search(self):
        url = self._get_url()
        user = self._get_authorised_user()

        data = {
            'description': 'Saved search',
            'endpoint': '/credits',
            'filters': [{'field': 'sender_name', 'value': 'Simon'}]
        }

        response = self.client.post(
            url, data=data, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        new_search = SavedSearch.objects.all().first()
        self.assertEqual(len(new_search.filters.all()), 1)
        self.assertEqual(new_search.user, user)


class UpdateSavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, _, self.security_staff = make_test_users()

    def _get_url(self, *args, **kwargs):
        return reverse('savedsearch-detail', args=args)

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]

    def test_update_saved_search(self):
        user = self._get_authorised_user()
        saved_search = SavedSearch.objects.create(
            user=user, description='Saved search', endpoint='/credits')
        SearchFilter.objects.create(
            saved_search=saved_search, field='sender_name', value='Simon'
        )

        url = self._get_url(saved_search.id)

        update = {
            'last_result_count': 12,
            'filters': [{'field': 'sender_name', 'value': 'Thomas'}]
        }

        response = self.client.patch(
            url, data=update, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        self.assertEqual(SavedSearch.objects.all().count(), 1)
        updated_search = SavedSearch.objects.all().first()
        self.assertEqual(updated_search.last_result_count, 12)
        self.assertEqual(len(updated_search.filters.all()), 1)
        self.assertEqual(updated_search.filters.all().first().value, 'Thomas')


class ListSavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, _, self.security_staff = make_test_users()

    def _get_url(self, *args, **kwargs):
        return reverse('savedsearch-list')

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]

    def test_users_can_only_access_their_own_searches(self):
        url = self._get_url()
        user1 = self._get_authorised_user()
        user2 = create_security_staff_user(name_and_password='security-staff-2')

        saved_search_user1 = SavedSearch.objects.create(
            user=user1, description='Saved search for user1', endpoint='/credits')

        saved_search_user2 = SavedSearch.objects.create(
            user=user2, description='Saved search for user2', endpoint='/credits')

        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user1)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            response.data['results'][0]['description'], saved_search_user1.description
        )

        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user2)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            response.data['results'][0]['description'], saved_search_user2.description
        )


class DeleteSavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, _, self.security_staff = make_test_users()

    def _get_url(self, *args, **kwargs):
        return reverse('savedsearch-detail', args=args)

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]

    def test_delete_saved_search(self):
        user = self._get_authorised_user()
        saved_search = SavedSearch.objects.create(
            user=user, description='Saved search', endpoint='/credits')
        SearchFilter.objects.create(
            saved_search=saved_search, field='sender_name', value='Simon'
        )

        url = self._get_url(saved_search.id)
        response = self.client.delete(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        self.assertEqual(SavedSearch.objects.all().count(), 0)

    def test_users_can_only_delete_their_own_searches(self):
        user1 = self._get_authorised_user()
        user2 = create_security_staff_user(name_and_password='security-staff-2')

        saved_search_user1 = SavedSearch.objects.create(
            user=user1, description='Saved search for user1')

        url = self._get_url(saved_search_user1.id)
        response = self.client.delete(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user2)
        )
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
