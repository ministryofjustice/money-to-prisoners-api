import datetime
import itertools

from django.urls import reverse_lazy
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin
from service.constants import NotificationTarget
from service.models import Notification


class NotificationsTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']
    url = reverse_lazy('notifications-list')

    def setUp(self):
        super().setUp()
        self.users = list(itertools.chain.from_iterable(
            make_test_users(clerks_per_prison=1).values())
        )

    def test_unauthenticated_can_see_public_notifications(self):
        Notification.objects.create(
            target=NotificationTarget.cashbook_all, level=30,
            headline='Test', message='Body',
            start='2017-11-29 11:00:00Z',
        )
        Notification.objects.create(
            target=NotificationTarget.cashbook_login, level=20, public=True,
            headline='Login', message='',
            start='2017-11-29 12:00:00Z',
        )
        response = self.client.get(self.url,  format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertDictEqual(response.data['results'][0], {
            'target': NotificationTarget.cashbook_login, 'level': 'info',
            'headline': 'Login', 'message': '',
            'start': '2017-11-29T12:00:00Z', 'end': None,
        })

    def test_any_user_can_see_all_notifications(self):
        Notification.objects.create(
            target=NotificationTarget.cashbook_all, level=30,
            headline='Test', message='Body',
            start='2017-11-29 11:00:00Z',
        )
        Notification.objects.create(
            target=NotificationTarget.cashbook_login, level=20, public=True,
            headline='Login', message='',
            start='2017-11-29 12:00:00Z',
        )
        for user in self.users:
            response = self.client.get(
                self.url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['count'], 2)
            self.assertDictEqual(response.data['results'][0], {
                'target': NotificationTarget.cashbook_login, 'level': 'info',
                'headline': 'Login', 'message': '',
                'start': '2017-11-29T12:00:00Z', 'end': None,
            })
            self.assertDictEqual(response.data['results'][1], {
                'target': NotificationTarget.cashbook_all, 'level': 'warning',
                'headline': 'Test', 'message': 'Body',
                'start': '2017-11-29T11:00:00Z', 'end': None,
            })

    def test_listing_notifications(self):
        user = self.users[0]

        response = self.client.get(
            self.url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertListEqual(response.data['results'], [])

        # notification started, but not ended
        Notification.objects.create(
            target=NotificationTarget.cashbook_all, level=30,
            headline='Test 1', message='Body',
            start='2017-11-29 12:00:00Z',
        )
        # notification started and ended
        Notification.objects.create(
            target=NotificationTarget.cashbook_all, level=20,
            headline='Test 2', message='',
            start='2017-11-29 12:00:00Z',
            end='2017-11-29 13:00:00Z',
        )
        # notification starting in future
        Notification.objects.create(
            target=NotificationTarget.cashbook_all, level=20,
            headline='Test 3', message='',
            start=timezone.now() + datetime.timedelta(days=1),
        )
        response = self.client.get(
            self.url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)
        self.assertDictEqual(response.data['results'][0], {
            'target': NotificationTarget.cashbook_all, 'level': 'warning',
            'headline': 'Test 1', 'message': 'Body',
            'start': '2017-11-29T12:00:00Z', 'end': None,
        })

    def test_filtering_notifications(self):
        user = self.users[0]

        Notification.objects.create(target=NotificationTarget.cashbook_all, level=30,
                                    headline='Test', message='Body',
                                    start='2017-11-29 12:00:00Z')
        Notification.objects.create(target=NotificationTarget.cashbook_login, level=20,
                                    headline='Login', message='',
                                    start='2017-11-29 13:00:00Z')

        response = self.client.get(
            self.url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 2)

        response = self.client.get(
            self.url + '?target__startswith=' + NotificationTarget.cashbook_login, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)

        response = self.client.get(
            self.url + '?target__startswith=other', format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(len(response.data['results']), 0)
