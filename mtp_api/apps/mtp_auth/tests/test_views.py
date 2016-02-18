import datetime
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.utils.timezone import now
from oauth2_provider.models import Application
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from mtp_auth.constants import BANK_ADMIN_OAUTH_CLIENT_ID, CASHBOOK_OAUTH_CLIENT_ID, \
    PRISONER_LOCATION_OAUTH_CLIENT_ID
from mtp_auth.models import FailedLoginAttempt
from prison.models import Prison
from .utils import AuthTestCaseMixin


class UserViewTestCase(APITestCase):
    fixtures = [
        'initial_groups.json',
        'test_prisons.json'
    ]

    def setUp(self):
        super(UserViewTestCase, self).setUp()
        (
            self.prison_clerks, self.prisoner_location_admins,
            self.bank_admins, self.refund_bank_admins,
            self.send_money_users,
        ) = make_test_users(clerks_per_prison=2)
        self.test_users = (
            self.prison_clerks + self.prisoner_location_admins +
            self.bank_admins + self.refund_bank_admins
        )

        self.prisons = Prison.objects.all()

    def _get_url(self, username):
        return reverse('user-detail', kwargs={'username': username})

    def test_cannot_access_data_when_not_logged_in(self):
        url = self._get_url('me')
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_access_others_data(self):
        """
        Returns 404 when trying to access other's user data.
        404 because we don't want to leak anything about our
        db.
        """
        logged_in_user = self.prison_clerks[0]
        self.client.force_authenticate(user=logged_in_user)

        for user in self.prison_clerks[1:]:
            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_access_my_data_including_managing_prisons(self):
        for user in self.prison_clerks:
            self.client.force_authenticate(user=user)

            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['pk'], user.pk)
            prison_ids = list(user.prisonusermapping.prisons.values_list('pk', flat=True))
            self.assertEqual(response.data['prisons'], prison_ids)

    def test_correct_permissions_returned(self):
        for user in self.test_users:
            self.client.force_authenticate(user=user)

            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['permissions'], user.get_all_permissions())

    def test_my_data_with_empty_prisons(self):
        users = \
            self.prisoner_location_admins + \
            self.bank_admins + self.refund_bank_admins

        for user in users:
            self.client.force_authenticate(user=user)

            url = self._get_url(user.username)
            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['pk'], user.pk)
            self.assertEqual(response.data['prisons'], [])


class UserApplicationValidationTestCase(APITestCase):
    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super(UserApplicationValidationTestCase, self).setUp()
        self.prison_clerks, self.users, self.bank_admins, _, _ = make_test_users()

    def test_prison_clerk_can_log_in_to_cashbook(self):
        response = self.client.post(
            reverse('oauth2_provider:token'),
            {
                'grant_type': 'password',
                'username': self.prison_clerks[0].username,
                'password': self.prison_clerks[0].username,
                'client_id': CASHBOOK_OAUTH_CLIENT_ID,
                'client_secret': CASHBOOK_OAUTH_CLIENT_ID,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_bank_admin_can_log_in_to_bank_admin(self):
        response = self.client.post(
            reverse('oauth2_provider:token'),
            {
                'grant_type': 'password',
                'username': self.bank_admins[0].username,
                'password': self.bank_admins[0].username,
                'client_id': BANK_ADMIN_OAUTH_CLIENT_ID,
                'client_secret': BANK_ADMIN_OAUTH_CLIENT_ID,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_prison_clerk_cannot_login_to_bank_admin(self):
        response = self.client.post(
            reverse('oauth2_provider:token'),
            {
                'grant_type': 'password',
                'username': self.prison_clerks[0].username,
                'password': self.prison_clerks[0].username,
                'client_id': BANK_ADMIN_OAUTH_CLIENT_ID,
                'client_secret': BANK_ADMIN_OAUTH_CLIENT_ID,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_bank_admin_cannot_login_to_cashbook(self):
        response = self.client.post(
            reverse('oauth2_provider:token'),
            {
                'grant_type': 'password',
                'username': self.bank_admins[0].username,
                'password': self.bank_admins[0].username,
                'client_id': CASHBOOK_OAUTH_CLIENT_ID,
                'client_secret': CASHBOOK_OAUTH_CLIENT_ID,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AccountLockoutTestCase(APITestCase):
    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks = make_test_users()[0]

    def pass_login(self, user, client):
        response = self.client.post(
            reverse('oauth2_provider:token'),
            {
                'grant_type': 'password',
                'username': user.username,
                'password': user.username,
                'client_id': client.client_id,
                'client_secret': client.client_secret,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def fail_login(self, user, client):
        response = self.client.post(
            reverse('oauth2_provider:token'),
            {
                'grant_type': 'password',
                'username': user.username,
                'password': 'incorrect-password',
                'client_id': client.client_id,
                'client_secret': client.client_secret,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_account_lockout_on_too_many_attempts(self):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
            self.fail_login(prison_clerk, cashbook_client)

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
        self.fail_login(prison_clerk, cashbook_client)

    def test_account_lockout_only_applies_for_a_period_of_time(self):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.fail_login(prison_clerk, cashbook_client)

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))

        future = now() + datetime.timedelta(seconds=settings.MTP_AUTH_LOCKOUT_LOCKOUT_PERIOD) \
            + datetime.timedelta(seconds=1)
        with mock.patch('mtp_auth.models.now') as mocked_now:
            mocked_now.return_value = future
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
            self.pass_login(prison_clerk, cashbook_client)

    def test_account_lockout_removed_on_successful_login(self):
        if not settings.MTP_AUTH_LOCKOUT_COUNT:
            return

        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT - 1):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
            self.fail_login(prison_clerk, cashbook_client)

        self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
        self.pass_login(prison_clerk, cashbook_client)
        self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
        self.assertEqual(FailedLoginAttempt.objects.filter(
            user=prison_clerk,
            application=cashbook_client,
        ).count(), 0)

    def test_account_lockout_only_applies_to_current_application(self):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)
        bank_admin_client = Application.objects.get(client_id=BANK_ADMIN_OAUTH_CLIENT_ID)
        prisoner_location_admin_client = Application.objects.get(client_id=PRISONER_LOCATION_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
            self.fail_login(prison_clerk, cashbook_client)
            self.fail_login(prison_clerk, bank_admin_client)

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, bank_admin_client))
        self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, prisoner_location_admin_client))

    def test_account_lockout_remains_if_successful_login_in_other_application(self):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)
        bank_admin_client = Application.objects.get(client_id=BANK_ADMIN_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.fail_login(prison_clerk, bank_admin_client)

        self.pass_login(prison_clerk, cashbook_client)

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, bank_admin_client))
        self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))


class ChangePasswordTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = [
        'initial_groups.json',
        'test_prisons.json'
    ]

    def setUp(self):
        super().setUp()
        self.user = make_test_users()[0][0]
        self.current_password = self.user.username

    def correct_password_change(self, new_password):
        return self.client.post(
            reverse('user-change-password'),
            {'old_password': self.current_password, 'new_password': new_password},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )

    def incorrect_password_attempt(self):
        return self.client.post(
            reverse('user-change-password'),
            {'old_password': 'wrong', 'new_password': 'fresh'},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )

    def test_change_password(self):
        new_password = 'fresh'
        self.correct_password_change(new_password)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(new_password))

    def test_requires_auth(self):
        response = self.client.post(
            reverse('user-change-password'),
            {'old_password': self.current_password, 'new_password': 'fresh'}
        )
        self.assertEqual(response.status_code, 401)
        self.assertTrue(self.user.check_password(self.current_password))

    def test_fails_with_incorrect_old_password(self):
        response = self.incorrect_password_attempt()
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.user.check_password(self.current_password))

    def test_account_lockout_on_too_many_attempts(self):
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
            self.incorrect_password_attempt()

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
        response = self.correct_password_change('new_password')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.user.check_password(self.current_password))

    def test_account_lockout_removed_on_successful_change(self):
        if not settings.MTP_AUTH_LOCKOUT_COUNT:
            return

        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT - 1):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
            self.incorrect_password_attempt()

        self.assertFalse(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
        self.correct_password_change('new_password')
        self.assertFalse(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
        self.assertEqual(FailedLoginAttempt.objects.filter(
            user=self.user,
            application=cashbook_client,
        ).count(), 0)
