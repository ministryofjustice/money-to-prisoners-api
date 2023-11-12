import random

from django.urls import reverse
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin
from security.models import MonitoredPartialEmailAddress


class MonitoredPartialEmailAddressTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()

        test_users = make_test_users(clerks_per_prison=0)
        # authorised
        self.fiu_user = random.choice(test_users['security_fiu_users'])
        # not authorised
        self.security_user = random.choice([
            user
            for user in test_users['security_staff']
            if 'fiu' not in user.username
        ])

        MonitoredPartialEmailAddress.objects.create(keyword='dog')
        MonitoredPartialEmailAddress.objects.create(keyword='cat')

    @classmethod
    def list_url(cls):
        return reverse('monitoredemailaddresses-list')

    @classmethod
    def detail_url(cls, keyword):
        return reverse('monitoredemailaddresses-detail', args=(keyword,))

    def test_fiu_can_create(self):
        response = self.client.post(
            self.list_url(),
            data='Mouse',
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.fiu_user),
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertEqual(MonitoredPartialEmailAddress.objects.count(), 3)
        MonitoredPartialEmailAddress.objects.get(keyword='mouse')
        self.assertFalse(MonitoredPartialEmailAddress.objects.filter(keyword='Mouse').exists())

    def test_invalid_create(self):
        response = self.client.post(
            self.list_url(),
            data='ab',
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.fiu_user),
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('keyword', response_data)

    def test_nonunique_create(self):
        response = self.client.post(
            self.list_url(),
            data='CAT',
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.fiu_user),
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertIn('keyword', response_data)

    def test_unauthorised_cannot_create(self):
        response = self.client.post(
            self.list_url(),
            data='Mouse',
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.security_user),
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(MonitoredPartialEmailAddress.objects.count(), 2)

    def test_fiu_can_list(self):
        response = self.client.get(
            self.list_url(),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.fiu_user),
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertListEqual(response.data['results'], ['cat', 'dog'])

    def test_unauthorised_cannot_list(self):
        response = self.client.get(
            self.list_url(),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.security_user),
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_fiu_can_delete(self):
        response = self.client.delete(
            self.detail_url('dog'),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.fiu_user),
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.content, b'')
        self.assertEqual(set(MonitoredPartialEmailAddress.objects.values_list('keyword', flat=True)), {'cat'})

    def test_unauthorised_cannot_delete(self):
        response = self.client.delete(
            self.detail_url('cat'),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.security_user),
        )
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)
        self.assertEqual(MonitoredPartialEmailAddress.objects.count(), 2)
