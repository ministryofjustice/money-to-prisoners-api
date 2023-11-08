from django.urls import reverse
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin
from mtp_auth.tests.mommy_recipes import create_security_staff_user
from security.models import SavedSearch, SearchFilter


class SavedSearchTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_staff = test_users['security_staff']

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_authorised_user(self):
        return self.security_staff[0]


class CreateSavedSearchTestCase(SavedSearchTestCase):
    def _get_url(self):
        return reverse('savedsearch-list')

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


class UpdateSavedSearchTestCase(SavedSearchTestCase):
    def _get_url(self, *args):
        return reverse('savedsearch-detail', args=args)

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


class ListSavedSearchTestCase(SavedSearchTestCase):
    def _get_url(self):
        return reverse('savedsearch-list')

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


class DeleteSavedSearchTestCase(SavedSearchTestCase):
    def _get_url(self, *args):
        return reverse('savedsearch-detail', args=args)

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
