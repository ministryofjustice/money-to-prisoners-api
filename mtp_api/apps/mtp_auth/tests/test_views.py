import base64
import datetime
import json
import logging
import random
from unittest import mock
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse, reverse_lazy
from django.utils.timezone import now
from model_mommy import mommy
from mtp_common.test_utils import silence_logger
from oauth2_provider.models import AccessToken, Application, RefreshToken
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, make_test_user_admins
from mtp_auth.constants import (
    ALL_OAUTH_CLIENT_IDS,
    BANK_ADMIN_OAUTH_CLIENT_ID, CASHBOOK_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, SEND_MONEY_CLIENT_ID
)
from mtp_auth.models import (
    PrisonUserMapping, Role, Flag,
    Login, FailedLoginAttempt,
    PasswordChangeRequest, AccountRequest,
    JobInformation,
)
from mtp_auth.tests.mommy_recipes import basic_user, create_prison_clerk
from mtp_auth.views import ResetPasswordView
from mtp_auth.tests.utils import AuthTestCaseMixin
from prison.models import Prison

User = get_user_model()


def random_case(string):
    return ''.join(
        char.upper() if random.randrange(2) else char.lower()
        for char in string
    )


def prison_set(user):
    return set(
        user.prisonusermapping.prisons.values_list('pk', flat=True)
        if hasattr(user, 'prisonusermapping') else []
    )


class JobInformationTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = [
        'initial_groups.json',
        'initial_types.json',
        'test_prisons.json',
    ]

    url = reverse_lazy('job-information-list')

    payload = {
        'title': 'Warden',
        'prison_estate': 'Private',
        'tasks': 'Run the show',
    }

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff'][0]

    def test_authorization_required_to_create_job_information(self):
        response = self.client.post(self.url, data=self.payload)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_can_create_a_job_information_entry(self):
        response = self.client.post(
            self.url,
            data=self.payload,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.security_staff)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data, self.payload)

    def test_will_not_create_with_missing_params(self):
        payload = {
            'title': 'Warden',
            'prison_estate': '',
            'tasks': 'Run the show',
        }
        response = self.client.post(
            self.url,
            data=payload,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.security_staff)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_id_added_to_job_information_record(self):
        self.client.post(
            self.url,
            data=self.payload,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.security_staff)
        )
        records = JobInformation.objects.all()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].user_id, self.security_staff.id)


class AuthBaseTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = [
        'initial_groups.json',
        'initial_types.json',
        'test_prisons.json',
    ]

    def assertNoPrisons(self, left_user, msg=None):  # noqa: N802
        left_prisons = prison_set(left_user)
        self.assertSetEqual(left_prisons, set(), msg=msg or 'User should not have any assigned prisons, but does')

    def assertSamePrisons(self, left_user, right_user, msg=None):  # noqa: N802
        left_prisons = prison_set(left_user)
        right_prisons = prison_set(right_user)
        self.assertSetEqual(left_prisons, right_prisons, msg=msg or 'Users do not have matching prison sets')

    def assertSubsetPrisons(self, left_user, right_user, msg=None):  # noqa: N802
        left_prisons = prison_set(left_user)
        right_prisons = prison_set(right_user)
        self.assertTrue(left_prisons.issubset(right_prisons), msg=msg or 'User prison set is not a subset')


class OauthTokenTestCase(AuthBaseTestCase):
    @classmethod
    def create_test_methods(cls):
        for client_id in ALL_OAUTH_CLIENT_IDS:
            method_name = client_id.replace('-', '_')
            setattr(cls, 'test_successful_login_with_%s' % method_name,
                    cls.create_successful_test_method(client_id, False))
            setattr(cls, 'test_successful_login_with_%s_without_case_sensitivity' % method_name,
                    cls.create_successful_test_method(client_id, True))
            setattr(cls, 'test_unsuccessful_login_with_%s' % method_name,
                    cls.create_unsuccessful_test_method(client_id))

    @classmethod
    def create_successful_test_method(cls, client_id, randomise_username_case):
        def test_successful_login(self):
            client = Application.objects.get(client_id=client_id)
            for mapping in client.applicationusermapping_set.all():
                username = mapping.user.username
                if randomise_username_case:
                    username = random_case(username)
                password = mapping.user.username
                response = self.client.post(
                    reverse('oauth2_provider:token'),
                    {
                        'grant_type': 'password',
                        'username': username,
                        'password': password,
                        'client_id': client.client_id,
                        'client_secret': client.client_secret,
                    }
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                response_data = response.json()
                self.assertEqual(AccessToken.objects.filter(token=response_data['access_token']).count(), 1)
                self.assertEqual(RefreshToken.objects.filter(token=response_data['refresh_token']).count(), 1)
            self.assertEqual(AccessToken.objects.count(), client.applicationusermapping_set.count())
            self.assertEqual(RefreshToken.objects.count(), client.applicationusermapping_set.count())

        return test_successful_login

    @classmethod
    def create_unsuccessful_test_method(cls, client_id):
        def test_unsuccessful_login(self):
            client = Application.objects.get(client_id=client_id)
            for mapping in client.applicationusermapping_set.all():
                username = mapping.user.username
                with silence_logger():
                    response = self.client.post(
                        reverse('oauth2_provider:token'),
                        {
                            'grant_type': 'password',
                            'username': username,
                            'password': 'incorrect-password',
                            'client_id': client.client_id,
                            'client_secret': client.client_secret,
                        }
                    )
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
                response_data = response.json()
                self.assertNotIn('access_token', response_data)
                self.assertNotIn('refresh_token', response_data)
            self.assertEqual(AccessToken.objects.count(), 0)
            self.assertEqual(RefreshToken.objects.count(), 0)

        return test_unsuccessful_login

    def setUp(self):
        super().setUp()
        make_test_users(clerks_per_prison=1)


OauthTokenTestCase.create_test_methods()


class RoleTestCase(AuthBaseTestCase):
    url = reverse_lazy('role-list')

    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=1)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.send_money_users = test_users['send_money_users']
        self.security_staff = test_users['security_staff']
        self.users_with_no_role = self.bank_admins + self.send_money_users
        test_uas = make_test_user_admins()
        self.cashbook_uas = test_uas['prison_clerk_uas']
        self.pla_uas = test_uas['prisoner_location_uas']
        self.bank_uas = test_uas['bank_admin_uas']
        self.security_uas = test_uas['security_fiu_uas']
        self.admin_users = self.cashbook_uas + self.pla_uas + self.bank_uas + self.security_uas

    def test_cannot_list_roles_when_not_logged_in(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def assertCanListRoles(self, user, expected_roles, url=None):  # noqa: N802
        response = self.client.get(
            url or self.url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        roles = response.data['results']
        self.assertSequenceEqual(
            sorted(role['name'] for role in roles),
            expected_roles,
        )
        return roles

    def test_can_all_list_roles(self):
        user = random.choice(self.admin_users)
        roles = self.assertCanListRoles(
            user,
            ['bank-admin', 'disbursement-admin', 'prison-clerk', 'prisoner-location-admin', 'security']
        )
        self.assertTrue(all(
            'application' in role and 'name' in role['application'] and 'client_id' in role['application']
            for role in roles
        ))

    def test_user_not_in_role_can_list_all_anyway(self):
        user = random.choice(self.users_with_no_role)
        self.assertCanListRoles(
            user,
            ['bank-admin', 'disbursement-admin', 'prison-clerk', 'prisoner-location-admin', 'security']
        )

    def test_user_not_in_role_cannot_mange_any(self):
        user = random.choice(self.users_with_no_role)
        self.assertCanListRoles(user, [], self.url + '?managed')

    def test_user_in_role_manages_only_same_role(self):
        user = random.choice(self.cashbook_uas)
        self.assertCanListRoles(user, ['prison-clerk'], self.url + '?managed')
        user = random.choice(self.bank_uas)
        self.assertCanListRoles(user, ['bank-admin'], self.url + '?managed')
        user = random.choice(self.pla_uas)
        self.assertCanListRoles(user, ['prisoner-location-admin'], self.url + '?managed')
        user = random.choice(self.security_uas)
        self.assertCanListRoles(user, ['security'], self.url + '?managed')


class GetUserTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=2)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.security_users = test_users['security_staff']
        self.send_money_users = test_users['send_money_users']
        self.test_users = (
            self.prison_clerks + self.prisoner_location_admins +
            self.bank_admins + self.refund_bank_admins + self.security_users
        )
        self.bank_uas = make_test_user_admins()['bank_admin_uas']

    def _get_url(self, username):
        return reverse('user-detail', kwargs={'username': username})

    def test_cannot_access_data_when_not_logged_in(self):
        url = self._get_url(self.prison_clerks[0].username)
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_access_others_data(self):
        """
        Returns 404 when trying to access other's user data.
        404 because we don't want to leak anything about our
        db.
        """
        logged_in_user = self.prison_clerks[0]

        for user in self.prison_clerks[1:] + self.prisoner_location_admins:
            url = self._get_url(user.username)
            with silence_logger('django.request', level=logging.ERROR):
                response = self.client.get(
                    url, format='json',
                    HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
                )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_access_my_data(self):
        for user in self.prison_clerks:
            url = self._get_url(user.username)
            response = self.client.get(
                url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['pk'], user.pk)

    def test_can_access_my_data_without_case_sensitivity(self):
        for user in self.prison_clerks:
            username = user.username
            while username == user.username:
                username = random_case(user.username)
            url = self._get_url(username)
            response = self.client.get(
                url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['pk'], user.pk)
            self.assertNotEqual(response.data['username'], username)

    def test_correct_permissions_returned(self):
        for user in self.test_users:
            url = self._get_url(user.username)
            response = self.client.get(
                url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertEqual(response.data['permissions'], user.get_all_permissions())

    def test_correct_roles_returned(self):
        roles = [['prison-clerk'], ['prison-clerk'], ['prison-clerk'], ['prison-clerk'],
                 ['prisoner-location-admin'], [], ['bank-admin'], ['security']]
        for user, roles in zip(self.test_users, roles):
            url = self._get_url(user.username)
            response = self.client.get(
                url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertListEqual(response.data['roles'], roles)

    def test_correct_prisons_returned(self):
        for user in self.prison_clerks:
            url = self._get_url(user.username)
            response = self.client.get(
                url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )
            self.assertListEqual(
                response.json()['prisons'],
                list(
                    {'nomis_id': prison.nomis_id,
                     'name': prison.name,
                     'pre_approval_required': prison.pre_approval_required}
                    for prison in user.prisonusermapping.prisons.all()
                )
            )

    def test_correct_flags_returned(self):
        for user in self.test_users:
            url = self._get_url(user.username)
            response = self.client.get(
                url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )
            self.assertListEqual(
                response.json()['flags'],
                ['hmpps-employee'] if user in self.security_users else []
            )

        user_1, user_2 = self.security_users[:2]
        Flag.objects.create(user=user_1, name='abc')
        Flag.objects.create(user=user_2, name='abc')
        Flag.objects.create(user=user_2, name='123')
        flags = [['abc', 'hmpps-employee'], ['123', 'abc', 'hmpps-employee']]
        for user, flags in zip(self.security_users[:2], flags):
            url = self._get_url(user.username)
            response = self.client.get(
                url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )
            self.assertListEqual(sorted(response.json()['flags']), flags)

    @mock.patch('mtp_auth.serializers.send_email')
    def test_all_valid_usernames_retrievable(self, mock_send_email):
        username = 'dotted.name'
        user_data = {
            'username': username,
            'first_name': 'New',
            'last_name': 'User',
            'email': 'user@mtp.local',
            'role': 'bank-admin',
        }
        response = self.client.post(
            reverse('user-list'),
            format='json',
            data=user_data,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.bank_uas[0])
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mock_send_email.call_count, 1)

        response = self.client.get(
            self._get_url(username),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.bank_uas[0])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], username)


class UserFlagTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=1)
        test_admins = make_test_user_admins()
        self.prison_clerk = test_users['prison_clerks'][0]
        self.user_url = reverse('user-detail', kwargs={'username': self.prison_clerk.username})
        self.flags_url = reverse('user-flags-list', kwargs={'user_username': self.prison_clerk.username})
        prison = self.prison_clerk.prisonusermapping.prisons.first()
        self.prison_clerk_ua = next(filter(
            lambda user: user.prisonusermapping.prisons.first() == prison,
            test_admins['prison_clerk_uas']
        ))
        self.another_prison_clerk_ua = next(filter(
            lambda user: user.prisonusermapping.prisons.first() != prison,
            test_admins['prison_clerk_uas']
        ))

    def get_flag_url(self, flag):
        return reverse('user-flags-detail', kwargs={
            'user_username': self.prison_clerk.username,
            'name': flag,
        })

    def assertCanListFlags(self, authorisation, sorted_flags):  # noqa: N802
        response = self.client.get(
            self.user_url,
            format='json', HTTP_AUTHORIZATION=authorisation
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertListEqual(sorted(response.json()['flags']), sorted_flags)
        response = self.client.get(
            self.flags_url,
            format='json', HTTP_AUTHORIZATION=authorisation
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertListEqual(sorted(response.json()['results']), sorted_flags)

    def assertCannotListFlags(self, authorisation, expected_status=status.HTTP_404_NOT_FOUND):  # noqa: N802
        with silence_logger('django.request', level=logging.ERROR):
            response = self.client.get(
                self.user_url,
                format='json', HTTP_AUTHORIZATION=authorisation
            )
        self.assertEqual(response.status_code, expected_status)
        with silence_logger('django.request', level=logging.ERROR):
            response = self.client.get(
                self.flags_url,
                format='json', HTTP_AUTHORIZATION=authorisation
            )
        self.assertEqual(response.status_code, expected_status)

    def assertCanSetFlag(self, authorisation, flag, expected_status=status.HTTP_201_CREATED):  # noqa: N802
        response = self.client.put(
            self.get_flag_url(flag),
            format='json', HTTP_AUTHORIZATION=authorisation
        )
        self.assertEqual(response.status_code, expected_status)
        self.assertDictEqual(response.json(), {})

    def assertCannotSetFlag(self, authorisation, flag, expected_status=status.HTTP_400_BAD_REQUEST):  # noqa: N802
        with silence_logger('django.request', level=logging.ERROR):
            response = self.client.put(
                self.get_flag_url(flag),
                format='json', HTTP_AUTHORIZATION=authorisation
            )
        self.assertEqual(response.status_code, expected_status)
        if expected_status == status.HTTP_400_BAD_REQUEST:
            self.assertIn('name', response.json())

    def assertCanRemoveFlag(self, authorisation, flag):  # noqa: N802
        response = self.client.delete(
            self.get_flag_url(flag),
            format='json', HTTP_AUTHORIZATION=authorisation
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(response.content)

    def assertCannotRemoveFlag(self, authorisation, flag):  # noqa: N802
        with silence_logger('django.request', level=logging.ERROR):
            response = self.client.delete(
                self.get_flag_url(flag),
                format='json', HTTP_AUTHORIZATION=authorisation
            )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_can_set_own_flags(self):
        prison_clerk_auth = self.get_http_authorization_for_user(self.prison_clerk)
        self.assertCanListFlags(prison_clerk_auth, [])
        self.assertCanSetFlag(prison_clerk_auth, 'flag1')
        self.assertCanListFlags(prison_clerk_auth, ['flag1'])
        self.assertCanSetFlag(prison_clerk_auth, 'flag1', status.HTTP_200_OK)
        self.assertCanListFlags(prison_clerk_auth, ['flag1'])
        self.assertCanSetFlag(prison_clerk_auth, 'FLAG1')
        self.assertCanListFlags(prison_clerk_auth, ['FLAG1', 'flag1'])

    def test_can_remove_own_flags(self):
        prison_clerk_auth = self.get_http_authorization_for_user(self.prison_clerk)
        Flag.objects.create(user=self.prison_clerk, name='flag1')
        Flag.objects.create(user=self.prison_clerk, name='flag2')
        self.assertCanRemoveFlag(prison_clerk_auth, 'flag1')
        self.assertCanListFlags(prison_clerk_auth, ['flag2'])
        self.assertCannotRemoveFlag(prison_clerk_auth, 'other')
        self.assertCanRemoveFlag(prison_clerk_auth, 'flag2')
        self.assertCannotRemoveFlag(prison_clerk_auth, 'flag2')
        self.assertFalse(Flag.objects.filter(user=self.prison_clerk).exists())

    def test_cannot_set_invalid_flag(self):
        prison_clerk_auth = self.get_http_authorization_for_user(self.prison_clerk)
        self.assertCannotSetFlag(prison_clerk_auth, ' ')
        self.assertCannotSetFlag(prison_clerk_auth, 'a 1')

    def test_invalid_methods_on_flag_detail(self):
        prison_clerk_auth = self.get_http_authorization_for_user(self.prison_clerk)
        response = self.client.post(
            self.get_flag_url('flag1'), data={'name': 'flag2'},
            format='json', HTTP_AUTHORIZATION=prison_clerk_auth
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        response = self.client.patch(
            self.get_flag_url('flag1'), data={'name': 'flag2'},
            format='json', HTTP_AUTHORIZATION=prison_clerk_auth
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_cannot_edit_flags_via_user_view(self):
        prison_clerk_auth = self.get_http_authorization_for_user(self.prison_clerk)
        Flag.objects.create(user=self.prison_clerk, name='flag1')
        response = self.client.patch(
            self.user_url, data={'flags': ['flag2', 'flag3'], 'first_name': 'New name'},
            format='json', HTTP_AUTHORIZATION=prison_clerk_auth
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertSetEqual(
            set(Flag.objects.filter(user=self.prison_clerk).values_list('name', flat=True)),
            {'flag1'}
        )

        prison_clerk_ua_auth = self.get_http_authorization_for_user(self.prison_clerk_ua)
        response = self.client.patch(
            self.user_url, data={'flags': ['flag2', 'flag3'], 'first_name': 'New name'},
            format='json', HTTP_AUTHORIZATION=prison_clerk_ua_auth
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertSetEqual(
            set(Flag.objects.filter(user=self.prison_clerk).values_list('name', flat=True)),
            {'flag1'}
        )

    def test_can_set_managed_flags(self):
        prison_clerk_ua_auth = self.get_http_authorization_for_user(self.prison_clerk_ua)
        self.assertCanListFlags(prison_clerk_ua_auth, [])
        self.assertCanSetFlag(prison_clerk_ua_auth, 'flag1')
        self.assertCanListFlags(prison_clerk_ua_auth, ['flag1'])
        self.assertCanSetFlag(prison_clerk_ua_auth, 'flag1', status.HTTP_200_OK)
        self.assertCanListFlags(prison_clerk_ua_auth, ['flag1'])
        self.assertCanSetFlag(prison_clerk_ua_auth, 'FLAG1')
        self.assertCanListFlags(prison_clerk_ua_auth, ['FLAG1', 'flag1'])

        response = self.client.get(
            reverse('user-flags-list', kwargs={'user_username': self.prison_clerk_ua.username}),
            format='json', HTTP_AUTHORIZATION=prison_clerk_ua_auth
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertListEqual(sorted(response.json()['results']), [], msg='Own flags modified!')

    def test_can_remove_managed_flags(self):
        prison_clerk_ua_auth = self.get_http_authorization_for_user(self.prison_clerk_ua)
        Flag.objects.create(user=self.prison_clerk, name='flag1')
        Flag.objects.create(user=self.prison_clerk, name='flag2')
        self.assertCanRemoveFlag(prison_clerk_ua_auth, 'flag1')
        self.assertCanListFlags(prison_clerk_ua_auth, ['flag2'])
        self.assertCannotRemoveFlag(prison_clerk_ua_auth, 'other')
        self.assertCanRemoveFlag(prison_clerk_ua_auth, 'flag2')
        self.assertCannotRemoveFlag(prison_clerk_ua_auth, 'flag2')
        self.assertFalse(Flag.objects.filter(user=self.prison_clerk).exists())

    def test_cannot_view_others_flags(self):
        another_prison_clerk_auth = self.get_http_authorization_for_user(self.another_prison_clerk_ua)
        self.assertCannotListFlags(another_prison_clerk_auth)

    def test_cannot_set_others_flags(self):
        another_prison_clerk_auth = self.get_http_authorization_for_user(self.another_prison_clerk_ua)
        self.assertCannotSetFlag(another_prison_clerk_auth, 'flag1', status.HTTP_404_NOT_FOUND)

    def test_cannot_remove_others_flags(self):
        another_prison_clerk_auth = self.get_http_authorization_for_user(self.another_prison_clerk_ua)
        Flag.objects.create(user=self.prison_clerk, name='flag1')
        self.assertCannotRemoveFlag(another_prison_clerk_auth, 'flag1')
        self.assertSetEqual(
            set(Flag.objects.filter(user=self.prison_clerk).values_list('name', flat=True)),
            {'flag1'}
        )


class ListUserTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=1)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.send_money_users = test_users['send_money_users']
        self.security_staff = test_users['security_staff']

        test_uas = make_test_user_admins()
        self.cashbook_uas = test_uas['prison_clerk_uas']
        self.pla_uas = test_uas['prisoner_location_uas']
        self.bank_uas = test_uas['bank_admin_uas']
        self.security_uas = test_uas['security_fiu_uas']

    def get_url(self):
        return reverse('user-list')

    def test_list_users_only_accessible_to_admins(self):
        response = self.client.get(
            self.get_url(),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.refund_bank_admins[0])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def assertCanListUsers(  # noqa: N802
        self, requester, allowed_client_ids, exact_prison_match=True, no_prison_match=False
    ):
        response = self.client.get(
            self.get_url(),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(requester)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for user_item in response.data['results']:
            user = User.objects.get(username=user_item['username'])
            user_client_ids = set(user.applicationusermapping_set.values_list('application__client_id', flat=True))
            self.assertTrue(allowed_client_ids.issuperset(user_client_ids),
                            msg='Listed user with unexpected application access')

            if exact_prison_match and not no_prison_match:
                self.assertSamePrisons(requester, user,
                                       msg='User Admin able to retrieve users without matching prisons')
            elif not no_prison_match:
                self.assertSubsetPrisons(requester, user,
                                         msg='User Admin able to retrieve users without matching prisons')
        return response.data['results']

    def test_list_users_in_same_role(self):
        self.assertCanListUsers(self.cashbook_uas[0], {'cashbook'})
        self.assertCanListUsers(self.bank_uas[0], {'bank-admin'})
        self.assertCanListUsers(self.pla_uas[0], {'noms-ops'})
        self.assertCanListUsers(self.security_uas[0], {'noms-ops'}, no_prison_match=True)

    def test_list_users_in_same_prison_cashbook_admin(self):
        users = self.assertCanListUsers(self.cashbook_uas[0], {'cashbook'})
        users = set(user['username'] for user in users)
        self.assertIn(self.cashbook_uas[0].username, users)
        self.assertIn(self.prison_clerks[0].username, users)
        self.assertNotIn(self.cashbook_uas[1].username, users)
        self.assertNotIn(self.prison_clerks[1].username, users)
        self.assertTrue(all(
            user.username not in users
            for user in (self.security_staff + self.security_uas)
        ))

    def test_list_users_in_same_prison_security_admin(self):
        users = self.assertCanListUsers(
            self.security_uas[1], {'noms-ops'}, no_prison_match=True
        )
        users = set(user['username'] for user in users)
        self.assertIn(self.security_uas[1].username, users)
        self.assertIn(self.security_staff[1].username, users)
        self.assertIn(self.security_uas[0].username, users)
        self.assertIn(self.security_staff[0].username, users)
        self.assertTrue(all(
            user.username not in users
            for user in (self.prison_clerks + self.cashbook_uas)
        ))

    def test_list_users_in_multiple_prisons(self):
        # create new cashbook users linked to all prisons
        multi_prison_users = [
            create_prison_clerk(name_and_password='multi-prison', prisons=Prison.objects.all()[:2])
            for _ in range(2)
        ]
        for cashbook_admin in self.cashbook_uas:
            users = self.assertCanListUsers(cashbook_admin, {'cashbook', 'noms-ops'}, exact_prison_match=False)
            users = [user['username'] for user in users]
            self.assertTrue(all(
                multi_prison_user.username in users
                for multi_prison_user in multi_prison_users
            ))

        # upgrade one user, they should only see the two new multi-prison users
        multi_prison_users[0].groups.add(Group.objects.get(name='UserAdmin'))
        users = self.assertCanListUsers(multi_prison_users[0], {'cashbook', 'noms-ops'}, exact_prison_match=True)
        self.assertSequenceEqual(
            sorted(user['username'] for user in users),
            sorted(multi_prison_user.username for multi_prison_user in multi_prison_users),
        )

    def test_list_users_includes_deactivated_users(self):
        self.client.delete(
            reverse('user-detail', kwargs={'username': self.refund_bank_admins[0].username}),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.bank_uas[0])
        )
        returned_users = self.assertCanListUsers(self.bank_uas[0], {'bank-admin'})

        queryset = User.objects.filter(groups=Role.objects.get(name='bank-admin').key_group)
        self.assertEqual(queryset.count(), len(returned_users))
        self.assertEqual(queryset.filter(is_active=False).count(), 1)

    def test_list_users_includes_locked_users(self):
        cashbook_app = Application.objects.get(client_id='cashbook')
        prison_clerk = self.prison_clerks[0]
        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            FailedLoginAttempt.objects.create(application=cashbook_app, user=prison_clerk)
        response = self.client.get(self.get_url(), format='json',
                                   HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.cashbook_uas[0]))
        users = response.json()['results']
        self.assertEqual(sum(1 if user['is_locked_out'] else 0 for user in users), 1)


@mock.patch('mtp_auth.serializers.send_email')
class CreateUserTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_uas = make_test_user_admins()
        self.cashbook_uas = test_uas['prison_clerk_uas']
        self.pla_uas = test_uas['prisoner_location_uas']
        self.bank_uas = test_uas['bank_admin_uas']
        self.security_uas = test_uas['security_fiu_uas']

    def get_url(self):
        return reverse('user-list')

    def test_normal_user_cannot_create_user(self, mock_send_email):
        test_users = make_test_users(clerks_per_prison=1)
        bank_admins = test_users['bank_admins']
        user_data = {
            'username': 'new-bank-admin',
            'first_name': 'New',
            'last_name': 'Bank Admin',
            'email': 'nba@mtp.local',
            'role': 'bank-admin',
        }
        response = self.client.post(
            self.get_url(),
            format='json',
            data=user_data,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(bank_admins[0])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)

    def assertUserCreated(  # noqa: N802
        self, mock_send_email,
        requester, user_data, client_id, groups, target_client_id=None, expected_login_link=None,
        assert_prisons_inherited=True
    ):
        response = self.client.post(
            self.get_url(),
            format='json',
            data=user_data,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(requester,
                                                                    client_id=client_id)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(all(
            user_data[key] == value
            for key, value in response.json().items()
            if key in ('username', 'first_name', 'last_name', 'email')
        ))

        target_client_id = target_client_id or client_id
        make_user_admin = user_data.pop('user_admin', False)
        user_data.pop('role', None)
        new_user = User.objects.get(**user_data)
        self.assertEqual(
            list(
                new_user.applicationusermapping_set.values_list('application__client_id', flat=True)
            ),
            [target_client_id]
        )
        self.assertEqual(
            set(new_user.groups.all()),
            set(groups)
        )
        if assert_prisons_inherited:
            self.assertSamePrisons(
                requester, new_user, msg='User Admin able to retrieve users without matching prisons'
            )
        else:
            self.assertNoPrisons(new_user, msg='New user should not have prisons associated')

        if make_user_admin:
            self.assertIn('UserAdmin', new_user.groups.values_list('name', flat=True))
        else:
            self.assertNotIn('UserAdmin', new_user.groups.values_list('name', flat=True))

        self.assertEqual(mock_send_email.call_count, 1)
        send_email_kwargs = mock_send_email.call_args_list[0].kwargs
        self.assertEqual(send_email_kwargs['personalisation']['username'], user_data['username'])
        self.assertEqual(send_email_kwargs['personalisation']['login_url'], expected_login_link)
        self.assertEqual(
            send_email_kwargs['personalisation']['service_name'],
            Application.objects.get(client_id=target_client_id).name.lower(),
        )

    def test_create_bank_admin(self, mock_send_email):
        user_data = {
            'username': 'new-bank-admin',
            'first_name': 'New',
            'last_name': 'Bank Admin',
            'email': 'nba@mtp.local',
            'role': 'bank-admin',
        }
        self.assertUserCreated(
            mock_send_email,
            self.bank_uas[0],
            user_data,
            'bank-admin',
            [Group.objects.get(name='BankAdmin'),
             Group.objects.get(name='RefundBankAdmin')],
            expected_login_link='http://localhost/bank-admin/',
        )

    def test_create_prisoner_location_admin(self, mock_send_email):
        user_data = {
            'username': 'new-location-admin',
            'first_name': 'New',
            'last_name': 'Location Admin',
            'email': 'nla@mtp.local',
            'role': 'prisoner-location-admin',
        }
        self.assertUserCreated(
            mock_send_email,
            self.pla_uas[0],
            user_data,
            'noms-ops',
            [Group.objects.get(name='PrisonerLocationAdmin')],
            expected_login_link='http://localhost/noms-ops/',
        )

    def test_create_security_staff(self, mock_send_email):
        user_data = {
            'username': 'new-security-staff',
            'first_name': 'New',
            'last_name': 'Security Staff',
            'email': 'nss@mtp.local',
            'role': 'security',
        }
        self.assertUserCreated(
            mock_send_email,
            self.security_uas[0],
            user_data,
            'noms-ops',
            [Group.objects.get(name='Security')],
            expected_login_link='http://localhost/noms-ops/',
        )

    def test_create_prison_clerk(self, mock_send_email):
        user_data = {
            'username': 'new-prison-clerk',
            'first_name': 'New',
            'last_name': 'Prison Clerk',
            'email': 'pc@mtp.local',
            'role': 'prison-clerk',
        }
        self.assertUserCreated(
            mock_send_email,
            self.cashbook_uas[0],
            user_data,
            'cashbook',
            [Group.objects.get(name='PrisonClerk')],
            expected_login_link='http://localhost/cashbook/',
        )

    def test_create_cashbook_user_admin(self, mock_send_email):
        user_data = {
            'username': 'new-cashbook-ua',
            'first_name': 'New',
            'last_name': 'Cashbook User Admin',
            'email': 'cua@mtp.local',
            'user_admin': True,
            'role': 'prison-clerk',
        }
        self.assertUserCreated(
            mock_send_email,
            self.cashbook_uas[0],
            user_data,
            'cashbook',
            [Group.objects.get(name='PrisonClerk'),
             Group.objects.get(name='UserAdmin')],
            expected_login_link='http://localhost/cashbook/',
        )

    def assertUserNotCreated(self, mock_send_email, requester, data):  # noqa: N802
        response = self.client.post(
            self.get_url(),
            format='json',
            data=data,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(requester)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_send_email.assert_not_called()
        return response

    def test_cannot_create_non_unique_username(self, mock_send_email):
        user_data = {
            'username': self.cashbook_uas[0].username,
            'first_name': 'New',
            'last_name': 'Cashbook User Admin 2',
            'email': 'cua@mtp.local',
            'user_admin': True,
            'role': 'prison-clerk',
        }
        self.assertUserNotCreated(mock_send_email, self.cashbook_uas[0], user_data)
        self.assertEqual(User.objects.filter(username=self.cashbook_uas[0].username).count(), 1)

    def test_username_case_sensitivity(self, mock_send_email):
        requester = self.cashbook_uas[0]
        username = 'A-User'
        user_data = {
            'username': username,
            'first_name': 'Title',
            'last_name': 'Case',
            'email': 'title-case@mtp.local',
            'role': 'prison-clerk',
        }
        response = self.client.post(
            self.get_url(),
            format='json',
            data=user_data,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(requester)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['username'], username)
        self.assertEqual(User.objects.filter(username__exact=username).count(), 1)
        self.assertEqual(mock_send_email.call_count, 1)
        mock_send_email.reset_mock()

        username = 'a-user'
        user_data = {
            'username': username,
            'first_name': 'Lower',
            'last_name': 'Case',
            'email': 'lower-case@mtp.local',
            'role': 'prison-clerk',
        }
        response = self.assertUserNotCreated(mock_send_email, requester, user_data)
        self.assertIn('username', response.json())
        self.assertEqual(User.objects.filter(username__exact=username).count(), 0)
        self.assertEqual(User.objects.filter(username__iexact=username).count(), 1)

    def test_cannot_create_non_unique_email(self, mock_send_email):
        user_data = {
            'username': 'new-cashbook-ua',
            'first_name': 'New',
            'last_name': 'Cashbook User Admin',
            'email': self.cashbook_uas[0].email,
            'user_admin': True,
            'role': 'prison-clerk',
        }
        self.assertUserNotCreated(mock_send_email, self.cashbook_uas[0], user_data)
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)

    def test_cannot_create_with_missing_fields(self, mock_send_email):
        user_data = {
            'username': 'new-cashbook-ua',
            'first_name': 'New',
            'last_name': 'Cashbook User Admin',
            'email': self.cashbook_uas[0].email,
            'user_admin': True,
            'role': 'prison-clerk',
        }
        for field in ['first_name', 'last_name', 'email']:
            data = user_data.copy()
            del data[field]
            self.assertUserNotCreated(mock_send_email, self.cashbook_uas[0], data)
            self.assertEqual(User.objects.filter(username=data['username']).count(), 0)

    def test_cannot_create_with_missing_role(self, mock_send_email):
        user_data = {
            'username': 'new-user',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'user@mtp.local',
            'role': None,
        }
        response = self.assertUserNotCreated(mock_send_email, self.cashbook_uas[0], user_data)
        self.assertIn('role', response.data)
        self.assertIn('Role must be specified', response.data['role'])
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)

    def test_cannot_create_with_unknown_role(self, mock_send_email):
        user_data = {
            'username': 'new-user',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'user@mtp.local',
            'role': 'unknown',
        }
        response = self.assertUserNotCreated(mock_send_email, self.cashbook_uas[0], user_data)
        self.assertIn('role', response.data)
        self.assertIn('Invalid role: unknown', response.data['role'])
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)

    def test_cannot_create_with_unmanaged_role(self, mock_send_email):
        user_data = {
            'username': 'new-user',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'user@mtp.local',
            'role': 'bank-admin',
        }
        response = self.assertUserNotCreated(mock_send_email, self.cashbook_uas[0], user_data)
        self.assertIn('role', response.data)
        self.assertIn('Invalid role: bank-admin', response.data['role'])
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)

    def test_fiu_created_user_does_not_inherit_prisons(self, mock_send_email):
        """
        Test any Prison instances assigned by FIU aren't inherited by the new user

        As of MTP-1824, FIU is managing all Security users through the UserAdmin group
        """
        user_data = {
            'username': 'new-security-staff',
            'first_name': 'New',
            'last_name': 'Security Staff',
            'email': 'nss@mtp.local',
            'role': 'security',
        }
        self.assertUserCreated(
            mock_send_email,
            self.security_uas[0],
            user_data,
            'noms-ops',
            [Group.objects.get(name='Security')],
            expected_login_link='http://localhost/noms-ops/',
            assert_prisons_inherited=False
        )

    def test_created_fiu_user_has_user_admin_group(self, mock_send_email):
        """
        Test new FIU instances have correct groups

        As of MTP-1824, FIU is managing all Security users through the UserAdmin group
        """
        user_data = {
            'username': 'new-security-staff',
            'first_name': 'New',
            'last_name': 'Security Staff',
            'email': 'nss@mtp.local',
            'role': 'security',
            'user_admin': True
        }
        self.assertUserCreated(
            mock_send_email,
            self.security_uas[0],
            user_data,
            'noms-ops',
            Group.objects.filter(name__in=['FIU', 'Security', 'UserAdmin']).all(),
            expected_login_link='http://localhost/noms-ops/',
            assert_prisons_inherited=False
        )


class UpdateUserTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=1)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.security_users = test_users['security_staff']

        test_uas = make_test_user_admins()
        self.cashbook_uas = test_uas['prison_clerk_uas']
        self.pla_uas = test_uas['prisoner_location_uas']
        self.bank_uas = test_uas['bank_admin_uas']
        self.security_uas = test_uas['security_fiu_uas']

    def get_url(self, username):
        return reverse('user-detail', kwargs={'username': username})

    def _update_user(self, requester, username, user_data):
        return self.client.patch(
            self.get_url(username),
            format='json',
            data=user_data,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(requester)
        )

    def assertUserUpdated(self, requester, username, user_data):  # noqa: N802
        response = self._update_user(requester, username, user_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_data.pop('user_admin', None)
        user_data.pop('role', None)
        User.objects.get(username=username, **user_data)
        return response

    def assertUserNotUpdated(self, requester, username, user_data):  # noqa: N802
        user = User.objects.get(username=username)
        original_user_data = {
            attr: getattr(user, attr, None) for attr in user_data.keys()
        }
        response = self._update_user(requester, username, user_data)
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)
        original_user_data.pop('user_admin', None)
        original_user_data.pop('role', None)
        User.objects.get(username=username, **original_user_data)
        return response

    def test_update_bank_admin_bank_user_admin_succeeds(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name',
        }
        self.assertUserUpdated(
            self.bank_uas[0],
            self.refund_bank_admins[0].username,
            user_data
        )

    def test_upgrade_normal_user_to_admin_succeeds(self):
        user_data = {
            'user_admin': True,
        }
        self.assertUserUpdated(
            self.bank_uas[0],
            self.refund_bank_admins[0].username,
            user_data
        )
        updated_user = User.objects.get(username=self.refund_bank_admins[0].username)
        self.assertIn('UserAdmin', updated_user.groups.values_list('name', flat=True))

    def test_upgrade_user_of_other_application_fails(self):
        user_data = {
            'user_admin': True,
        }
        with silence_logger('django.request', level=logging.ERROR):
            self.assertUserNotUpdated(
                self.bank_uas[0],
                self.prisoner_location_admins[0].username,
                user_data
            )
        updated_user = User.objects.get(username=self.prisoner_location_admins[0].username)
        self.assertNotIn('UserAdmin', updated_user.groups.values_list('name', flat=True))

    def test_downgrade_admin_user_to_normal_succeeds(self):
        user_data = {
            'user_admin': False,
        }
        self.assertUserUpdated(
            self.bank_uas[0],
            self.bank_uas[1].username,
            user_data
        )
        updated_user = User.objects.get(username=self.bank_uas[1].username)
        self.assertNotIn('UserAdmin', updated_user.groups.values_list('name', flat=True))

    def test_downgrade_self_fails(self):
        user_data = {
            'user_admin': False,
        }
        with silence_logger('django.request', level=logging.ERROR):
            response = self.assertUserNotUpdated(
                self.bank_uas[0],
                self.bank_uas[0].username,
                user_data
            )
        updated_user = User.objects.get(username=self.bank_uas[0].username)
        self.assertIn('UserAdmin', updated_user.groups.values_list('name', flat=True))
        self.assertIn('Cannot change own access permissions', response.data)

    def test_update_bank_admin_as_cashbook_user_admin_fails(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name',
        }
        with silence_logger('django.request', level=logging.ERROR):
            self.assertUserNotUpdated(
                self.cashbook_uas[0],
                self.refund_bank_admins[0].username,
                user_data
            )

    def test_update_user_as_normal_user_fails(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name',
        }
        with silence_logger('django.request', level=logging.ERROR):
            self.assertUserNotUpdated(
                self.refund_bank_admins[0],
                self.bank_admins[0].username,
                user_data
            )

    def test_update_self_as_normal_user_succeeds(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name',
            'email': 'ba@mtp.local',
        }
        self.assertUserUpdated(
            self.bank_admins[0],
            self.bank_admins[0].username,
            user_data
        )

    def test_cannot_deactivate_self(self):
        user_data = {
            'is_active': False,
        }
        self.assertUserNotUpdated(
            self.security_users[0],
            self.security_users[0].username,
            user_data
        )

    def test_update_prison_clerk_in_same_prison_succeeds(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name',
        }
        self.assertUserUpdated(
            self.cashbook_uas[0],
            self.prison_clerks[0].username,
            user_data
        )

    def test_update_prison_clerk_in_different_prison_fails(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name',
        }
        with silence_logger('django.request', level=logging.ERROR):
            self.assertUserNotUpdated(
                self.cashbook_uas[1],
                self.prison_clerks[0].username,
                user_data
            )

    def test_can_update_username_case(self):
        requester = self.bank_uas[0]
        existing_username = self.bank_uas[1].username
        new_username = existing_username.upper()
        response = self._update_user(requester, existing_username, {
            'username': new_username
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['username'], new_username)
        self.assertEqual(User.objects.filter(username__exact=existing_username).count(), 0)
        self.assertEqual(User.objects.filter(username__exact=new_username).count(), 1)

    def test_cannot_update_username_to_non_unique(self):
        requester = self.bank_uas[0]
        existing_username = self.bank_uas[1].username
        new_username = requester.username
        response = self._update_user(requester, existing_username, {
            'username': new_username
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.json())
        self.assertEqual(User.objects.filter(username__exact=existing_username).count(), 1)
        self.assertEqual(User.objects.filter(username__exact=new_username).count(), 1)

    def test_cannot_update_username_to_non_unique_by_case(self):
        requester = self.bank_uas[0]
        existing_username = self.bank_uas[1].username
        new_username = requester.username.upper()
        response = self._update_user(requester, existing_username, {
            'username': new_username
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.json())
        self.assertEqual(User.objects.filter(username__exact=existing_username).count(), 1)
        self.assertEqual(User.objects.filter(username__exact=new_username).count(), 0)
        self.assertEqual(User.objects.filter(username__iexact=new_username).count(), 1)

    def test_cannot_update_non_unique_email(self):
        user_data = {
            'email': self.bank_uas[0].email
        }
        self.assertUserNotUpdated(
            self.bank_uas[0],
            self.refund_bank_admins[0].username,
            user_data
        )

    def test_can_unlock_user(self):
        cashbook_app = Application.objects.get(client_id='cashbook')
        prison_clerk = self.prison_clerks[0]
        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            FailedLoginAttempt.objects.create(application=cashbook_app, user=prison_clerk)
        detail_url = self.get_url(prison_clerk.username)
        response = self.client.get(detail_url, format='json',
                                   HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.cashbook_uas[0]))
        self.assertTrue(response.json()['is_locked_out'])
        response = self.client.patch(detail_url, format='json',
                                     data={'is_locked_out': False},
                                     HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.cashbook_uas[0]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()['is_locked_out'])

    def test_can_change_admin_level_in_own_app(self):
        user_data = {
            'user_admin': True,
        }
        self.assertUserUpdated(
            self.cashbook_uas[0],
            self.prison_clerks[0].username,
            user_data
        )
        updated_user = User.objects.get(username=self.prison_clerks[0].username)
        groups = set(updated_user.groups.values_list('name', flat=True))
        self.assertIn('UserAdmin', groups)
        self.assertIn('PrisonClerk', groups)
        self.assertNotIn('Security', groups)

    def test_cannot_change_own_role(self):
        user_data = {
            'role': 'prison-clerk'
        }
        with silence_logger('django.request', level=logging.ERROR):
            response = self.assertUserNotUpdated(
                self.security_uas[1],
                self.security_uas[1].username,
                user_data
            )
        updated_user = User.objects.get(username=self.security_uas[1].username)
        self.assertNotIn('PrisonClerk', updated_user.groups.values_list('name', flat=True))
        self.assertIn('Invalid role: prison-clerk', response.data['role'])

    def test_cannot_change_to_unknown_role(self):
        user_data = {
            'role': 'unknown'
        }
        with silence_logger('django.request', level=logging.ERROR):
            response = self.assertUserNotUpdated(
                self.cashbook_uas[0],
                self.prison_clerks[0].username,
                user_data
            )
        updated_user = User.objects.get(username=self.prison_clerks[0].username)
        self.assertIn('PrisonClerk', updated_user.groups.values_list('name', flat=True))
        self.assertIn('role', response.data)
        self.assertIn('Invalid role: unknown', response.data['role'])

    def test_cannot_change_to_unmanaged_role(self):
        user_data = {
            'role': 'bank-admin'
        }
        with silence_logger('django.request', level=logging.ERROR):
            response = self.assertUserNotUpdated(
                self.cashbook_uas[0],
                self.prison_clerks[0].username,
                user_data
            )
        updated_user = User.objects.get(username=self.prison_clerks[0].username)
        self.assertIn('PrisonClerk', updated_user.groups.values_list('name', flat=True))
        self.assertIn('role', response.data)
        self.assertIn('Invalid role: bank-admin', response.data['role'])

    def test_cannot_change_role_in_other_prison(self):
        user_data = {
            'role': 'security'
        }
        with silence_logger('django.request', level=logging.ERROR):
            self.assertUserNotUpdated(
                self.cashbook_uas[0],
                self.prison_clerks[1].username,
                user_data
            )
        updated_user = User.objects.get(username=self.prison_clerks[1].username)
        groups = set(updated_user.groups.values_list('name', flat=True))
        self.assertIn('PrisonClerk', groups)
        self.assertNotIn('Security', groups)

    def test_cannot_change_role_in_own_prison_but_different_app(self):
        user_data = {
            'role': 'prison-clerk'
        }
        with silence_logger('django.request', level=logging.ERROR):
            self.assertUserNotUpdated(
                self.cashbook_uas[0],
                self.security_users[1].username,
                user_data
            )
        updated_user = User.objects.get(username=self.security_users[1].username)
        groups = set(updated_user.groups.values_list('name', flat=True))
        self.assertNotIn('UserAdmin', groups)
        self.assertIn('Security', groups)
        self.assertNotIn('PrisonClerk', groups)

    def test_update_prison_for_security_user(self):
        user = self.security_users[1]
        current_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            user
        ).all()
        new_prison = Prison.objects.exclude(
            nomis_id__in=current_prisons.values_list('nomis_id', flat=True)
        ).first()
        user_data = {
            'prisons': [{'nomis_id': new_prison.nomis_id}]
        }
        response = self._update_user(user, user.username, user_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_user = User.objects.get(username=user.username)
        updated_prison = PrisonUserMapping.objects.get_prison_set_for_user(
            updated_user
        )
        self.assertEqual(len(updated_prison), 1)
        self.assertEqual(updated_prison.first(), new_prison)

    def test_update_multiple_prisons_for_security_user(self):
        user = self.security_users[1]
        new_prisons = Prison.objects.all()
        user_data = {
            'prisons': [
                {'nomis_id': prison.nomis_id} for prison in new_prisons
            ]
        }
        response = self._update_user(user, user.username, user_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_user = User.objects.get(username=user.username)
        updated_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            updated_user
        )
        self.assertEqual(len(updated_prisons), len(new_prisons))
        self.assertEqual(
            set(updated_prisons.values_list('nomis_id', flat=True)),
            set(new_prisons.values_list('nomis_id', flat=True))
        )

    def test_remove_all_prisons_for_security_user(self):
        user = self.security_users[1]
        user_data = {'prisons': []}
        response = self._update_user(user, user.username, user_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_user = User.objects.get(username=user.username)
        updated_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            updated_user
        )
        self.assertEqual(len(updated_prisons), 0)

    def test_user_update_without_prisons_does_not_remove_all(self):
        user = self.security_users[1]
        current_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            user
        ).all()
        user_data = {}
        response = self._update_user(user, user.username, user_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_user = User.objects.get(username=user.username)
        updated_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            updated_user
        )
        self.assertEqual(len(updated_prisons), len(current_prisons))

    def test_cannot_update_prison_set_for_security_user_admin(self):
        user = self.security_uas[1]
        current_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            user
        ).all()
        new_prison = Prison.objects.exclude(
            nomis_id__in=current_prisons.values_list('nomis_id', flat=True)
        ).first()
        user_data = {
            'prisons': [{'nomis_id': new_prison.nomis_id}]
        }
        response = self._update_user(user, user.username, user_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        updated_user = User.objects.get(username=user.username)
        updated_prison = PrisonUserMapping.objects.get_prison_set_for_user(
            updated_user
        ).all()
        self.assertEqual(
            set(updated_prison.values_list('nomis_id', flat=True)),
            set(current_prisons.values_list('nomis_id', flat=True))
        )

    def test_cannot_update_prison_set_for_cashbook_user(self):
        user = self.prison_clerks[1]
        current_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            user
        ).all()
        new_prison = Prison.objects.exclude(
            nomis_id__in=current_prisons.values_list('nomis_id', flat=True)
        ).first()
        user_data = {
            'prisons': [{'nomis_id': new_prison.nomis_id}]
        }
        response = self._update_user(user, user.username, user_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        updated_user = User.objects.get(username=user.username)
        updated_prison = PrisonUserMapping.objects.get_prison_set_for_user(
            updated_user
        ).all()
        self.assertEqual(
            set(updated_prison.values_list('nomis_id', flat=True)),
            set(current_prisons.values_list('nomis_id', flat=True))
        )

    def test_updated_user_adding_fiu_group_also_adds_user_admin_group(self):
        """
        Test user added to FIU group also has UserAdmin group

        As of MTP-1824, FIU is managing all Security users through the UserAdmin group
        """
        user = self.security_users[1]
        requesting_user = self.security_uas[0]
        current_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            user
        ).all()
        user_data = {'user_admin': True}
        self.assertUserUpdated(requesting_user, user.username, user_data)
        updated_user = User.objects.get(username=user.username)
        self.assertSequenceEqual(
            updated_user.groups.order_by('name').values_list('name', flat=True),
            ['FIU', 'Security', 'UserAdmin']
        )
        updated_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            updated_user
        ).all()
        self.assertEqual(set(current_prisons), set(updated_prisons))

    def test_update_user_passing_role_adding_fiu_group_also_adds_user_admin_group(self):
        """
        Test user added to FIU group also has UserAdmin group

        As of MTP-1824, FIU is managing all Security users through the UserAdmin group
        """
        user = self.security_users[1]
        requesting_user = self.security_uas[0]
        user_data = {
            'user_admin': True,
            'role': 'security',
        }

        self.assertUserUpdated(requesting_user, user.username, user_data)

        updated_user = User.objects.get(username=user.username)
        self.assertSequenceEqual(
            updated_user.groups.order_by('name').values_list('name', flat=True),
            ['FIU', 'Security', 'UserAdmin']
        )

    def test_updated_user_removing_fiu_group_also_removes_user_admin_group(self):
        """
        Test user removed from FIU group also has UserAdmin group

        As of MTP-1824, FIU is managing all Security users through the UserAdmin group
        """
        user = self.security_uas[1]
        requesting_user = self.security_uas[0]
        current_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            user
        ).all()
        user_data = {'user_admin': False}
        self.assertUserUpdated(requesting_user, user.username, user_data)
        updated_user = User.objects.get(username=user.username)
        self.assertSequenceEqual(
            updated_user.groups.values_list('name', flat=True),
            ['Security']
        )
        updated_prisons = PrisonUserMapping.objects.get_prison_set_for_user(
            updated_user
        ).all()
        self.assertEqual(set(current_prisons), set(updated_prisons))


class DeleteUserTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=1)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']

        test_uas = make_test_user_admins()
        self.cashbook_uas = test_uas['prison_clerk_uas']
        self.pla_uas = test_uas['prisoner_location_uas']
        self.bank_uas = test_uas['bank_admin_uas']

    def get_url(self, username):
        return reverse('user-detail', kwargs={'username': username})

    def _delete_user(self, requester, username):
        self.client.delete(
            self.get_url(username),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(requester)
        )

    def assertUserDeleted(self, requester, username):  # noqa: N802
        self._delete_user(requester, username)
        self.assertFalse(User.objects.get_by_natural_key(username).is_active)

    def assertUserNotDeleted(self, requester, username):  # noqa: N802
        with silence_logger('django.request', level=logging.ERROR):
            self._delete_user(requester, username)
        self.assertTrue(User.objects.get_by_natural_key(username).is_active)

    def test_delete_bank_admin_bank_user_admin_succeeds(self):
        self.assertUserDeleted(
            self.bank_uas[0],
            self.refund_bank_admins[0].username
        )

    def test_delete_bank_admin_bank_user_admin_succeeds_without_case_sensitivity(self):
        self.assertUserDeleted(
            self.bank_uas[0],
            self.refund_bank_admins[0].username.upper()
        )

    def test_delete_bank_admin_as_cashbook_user_admin_fails(self):
        self.assertUserNotDeleted(
            self.cashbook_uas[0],
            self.refund_bank_admins[0].username
        )

    def test_delete_user_as_normal_user_fails(self):
        self.assertUserNotDeleted(
            self.bank_admins[0],
            self.refund_bank_admins[0].username
        )

    def test_delete_prison_clerk_in_same_prison_succeeds(self):
        self.assertUserDeleted(
            self.cashbook_uas[0],
            self.prison_clerks[0].username
        )

    def test_delete_prison_clerk_in_same_prison_succeeds_without_case_sensitivity(self):
        self.assertUserDeleted(
            self.cashbook_uas[0],
            self.prison_clerks[0].username.upper()
        )

    def test_delete_prison_clerk_in_different_prison_fails(self):
        self.assertUserNotDeleted(
            self.cashbook_uas[1],
            self.prison_clerks[0].username
        )

    def test_user_deleting_self_allowed(self):
        self.assertUserDeleted(
            self.cashbook_uas[0],
            self.cashbook_uas[0].username
        )


class UserApplicationValidationTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.applications = (
            CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
            BANK_ADMIN_OAUTH_CLIENT_ID, SEND_MONEY_CLIENT_ID
        )

        self.users_and_apps = (
            (test_users['prison_clerks'], CASHBOOK_OAUTH_CLIENT_ID),
            (test_users['prisoner_location_admins'], NOMS_OPS_OAUTH_CLIENT_ID),
            (test_users['bank_admins'], BANK_ADMIN_OAUTH_CLIENT_ID),
            (test_users['refund_bank_admins'], BANK_ADMIN_OAUTH_CLIENT_ID),
            (test_users['disbursement_bank_admins'], BANK_ADMIN_OAUTH_CLIENT_ID),
            (test_users['send_money_users'], SEND_MONEY_CLIENT_ID),
            (test_users['security_staff'], NOMS_OPS_OAUTH_CLIENT_ID),
        )

    def _create_basic_auth(self, client_id, client_secret):
        creds = base64.b64encode(bytes('%s:%s' % (client_id, client_secret), 'utf8')).decode('utf-8')
        return 'Basic %s' % creds

    def login(self, username, application_client_id, ignored_usernames=()):
        with mock.patch.object(Login, 'ignored_usernames', set(ignored_usernames)):
            return self.client.post(
                reverse('oauth2_provider:token'),
                {
                    'grant_type': 'password',
                    'username': username,
                    'password': username,
                },
                HTTP_AUTHORIZATION=self._create_basic_auth(application_client_id, application_client_id)
            )

    def assertCanLogin(self, username, application_client_id):  # noqa: N802
        response = self.login(username, application_client_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg='User %s should not be allowed into %s' % (
            username, application_client_id
        ))
        login = Login.objects.order_by('-created').first()
        self.assertEqual(login.user.username, username)
        self.assertEqual(login.application.client_id, application_client_id)

    def assertCannotLogin(self, username, application_client_id):  # noqa: N802
        logins = Login.objects.count()
        response = self.login(username, application_client_id)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg='User %s should be allowed into %s' % (
            username, application_client_id
        ))
        self.assertEqual(logins, Login.objects.count(), 'Login should not have been counted')

    def test_users_can_log_into_own_application(self):
        for user_list, allowed_application in self.users_and_apps:
            self.assertCanLogin(random.choice(user_list).username, allowed_application)

    def test_users_cannot_log_into_other_applications(self):
        for user_list, allowed_application in self.users_and_apps:
            for application in self.applications:
                if application == allowed_application:
                    continue
                self.assertCannotLogin(random.choice(user_list).username, application)

    def test_special_logins_ignored(self):
        (user, *_), application = self.users_and_apps[5]
        logins = Login.objects.count()
        self.login(user.username, application, (user.username,))
        self.assertEqual(logins, Login.objects.count(), 'Login should not have been counted')


@mock.patch('mtp_auth.models.send_email')
class AccountLockoutTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        self.prison_clerks = make_test_users()['prison_clerks']

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
        with silence_logger():
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
        return response

    def test_account_lockout_on_too_many_attempts(self, mock_send_email):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for i in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
            response = self.fail_login(prison_clerk, cashbook_client)
            if i + 1 == settings.MTP_AUTH_LOCKOUT_COUNT - 1:
                self.assertEqual(response.content, b'{"error": "lockout_imminent"}')

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
        response = self.fail_login(prison_clerk, cashbook_client)
        self.assertEqual(response.content, b'{"error": "locked_out"}')
        self.assertEqual(mock_send_email.call_count, 1)

    def test_account_lockout_on_too_many_attempts_without_case_sensitivity(self, mock_send_email):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        original_username = prison_clerk.username
        usernames = set()
        while len(usernames) < settings.MTP_AUTH_LOCKOUT_COUNT:
            usernames.add(random_case(original_username))

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            prison_clerk.username = usernames.pop()
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
            self.fail_login(prison_clerk, cashbook_client)

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
        self.fail_login(prison_clerk, cashbook_client)
        self.assertEqual(mock_send_email.call_count, 1)

    def test_account_lockout_only_applies_for_a_period_of_time(self, mock_send_email):
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
        self.assertEqual(mock_send_email.call_count, 1)

    def test_account_lockout_removed_on_successful_login(self, mock_send_email):
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
        self.assertEqual(mock_send_email.call_count, 0)

    def test_account_lockout_only_applies_to_current_application(self, mock_send_email):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)
        bank_admin_client = Application.objects.get(client_id=BANK_ADMIN_OAUTH_CLIENT_ID)
        prisoner_location_admin_client = Application.objects.get(client_id=NOMS_OPS_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
            self.fail_login(prison_clerk, cashbook_client)
            self.fail_login(prison_clerk, bank_admin_client)

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, bank_admin_client))
        self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, prisoner_location_admin_client))
        self.assertEqual(mock_send_email.call_count, 2)

    def test_account_lockout_remains_if_successful_login_in_other_application(self, mock_send_email):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)
        bank_admin_client = Application.objects.get(client_id=BANK_ADMIN_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.fail_login(prison_clerk, bank_admin_client)

        self.pass_login(prison_clerk, cashbook_client)

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(prison_clerk, bank_admin_client))
        self.assertFalse(FailedLoginAttempt.objects.is_locked_out(prison_clerk, cashbook_client))
        self.assertEqual(mock_send_email.call_count, 1)

    def test_email_sent_when_account_locked(self, mock_send_email):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT - 1):
            self.fail_login(prison_clerk, cashbook_client)
        self.assertEqual(mock_send_email.call_count, 0, msg='Email should not be sent')
        self.fail_login(prison_clerk, cashbook_client)
        self.assertEqual(mock_send_email.call_count, 1, msg='Email should be sent')
        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.fail_login(prison_clerk, cashbook_client)
        self.assertEqual(mock_send_email.call_count, 1, msg='Only one email should be sent')

        send_email_kwargs = mock_send_email.call_args_list[-1].kwargs
        self.assertEqual(send_email_kwargs['personalisation']['service_name'], cashbook_client.name.lower())


class ChangePasswordTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_test_users()['prison_clerks'][0]
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
            {'old_password': 'wrong', 'new_password': 'freshpass'},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )

    def test_change_password(self):
        new_password = 'freshpass'
        response = self.correct_password_change(new_password)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password(new_password))

    def test_requires_auth(self):
        response = self.client.post(
            reverse('user-change-password'),
            {'old_password': self.current_password, 'new_password': 'freshpass'}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(self.user.check_password(self.current_password))

    def test_fails_with_incorrect_old_password(self):
        response = self.incorrect_password_attempt()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(self.user.check_password(self.current_password))

    @mock.patch('mtp_auth.models.send_email')
    def test_account_lockout_on_too_many_attempts(self, mock_send_email):
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
            self.incorrect_password_attempt()

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
        self.assertEqual(mock_send_email.call_count, 1)

        response = self.correct_password_change('new_password')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
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


@mock.patch('mtp_auth.views.send_email')
class ResetPasswordTestCase(AuthBaseTestCase):
    reset_url = reverse_lazy('user-reset-password')

    def setUp(self):
        super().setUp()
        self.user = make_test_users()['prison_clerks'][0]
        self.current_password = 'Password321='
        self.user.set_password(self.current_password)
        self.user.save()

    def assertErrorResponse(self, mock_send_email, response, error_dict):  # noqa: N802
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        error = json.loads(response.content.decode('utf-8')).get('errors', {})
        for key, value in error_dict.items():
            self.assertIn(key, error)
            self.assertSequenceEqual(error[key], value)
        user = authenticate(username=self.user.username, password=self.current_password)
        self.assertEqual(self.user.username, getattr(user, 'username', None),
                         msg='Cannot log in with old password')
        self.assertEqual(PasswordChangeRequest.objects.all().count(), 0,
                         msg='Password change request should not be created')
        mock_send_email.assert_not_called()

    def test_unknown_user(self, mock_send_email):
        response = self.client.post(self.reset_url, {'username': 'unknown'})
        self.assertErrorResponse(mock_send_email, response, {
            'username': [ResetPasswordView.error_messages['not_found']],
        })

    def test_incorrect_username(self, mock_send_email):
        username = self.user.username
        if '-' in username:
            username = username.replace('-', '_')
        elif '_' in username:
            username = username.replace('_', '-')
        else:
            username += '_'
        response = self.client.post(self.reset_url, {'username': username})
        self.assertErrorResponse(mock_send_email, response, {
            'username': [ResetPasswordView.error_messages['not_found']],
        })

    def test_unable_to_reset_immutable_user(self, mock_send_email):
        username = 'send-money'
        try:
            User.objects.get(username=username)
        except User.DoesNotExist:
            self.fail()
        response = self.client.post(self.reset_url, {'username': username})
        self.assertErrorResponse(mock_send_email, response, {
            'username': [ResetPasswordView.error_messages['not_found']],
        })

    def test_user_with_no_email(self, mock_send_email):
        self.user.email = ''
        self.user.save()
        response = self.client.post(self.reset_url, {'username': self.user.username})
        self.assertErrorResponse(mock_send_email, response, {
            'username': [ResetPasswordView.error_messages['no_email']],
        })

    def test_user_with_non_unique_email(self, mock_send_email):
        other_user = User.objects.exclude(pk=self.user.pk).first()
        self.user.email = other_user.email.title()
        self.user.save()
        response = self.client.post(self.reset_url, {'username': self.user.email})
        self.assertErrorResponse(mock_send_email, response, {
            'username': [ResetPasswordView.error_messages['multiple_found']],
        })

    def test_locked_user(self, mock_send_email):
        app = Application.objects.first()
        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            FailedLoginAttempt.objects.create(user=self.user, application=app)
        response = self.client.post(self.reset_url, {'username': self.user.username})
        self.assertErrorResponse(mock_send_email, response, {
            'username': [ResetPasswordView.error_messages['locked_out']],
        })

    def assertPasswordReset(self, mock_send_email, username):  # noqa: N802
        response = self.client.post(self.reset_url, {'username': username})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        user = authenticate(username=self.user.username, password=self.current_password)
        self.assertIsNone(user, msg='Password was not changed')

        self.assertEqual(PasswordChangeRequest.objects.all().count(), 0,
                         msg='Password change request should not be created')

        self.assertEqual(mock_send_email.call_count, 1)
        send_email_kwargs = mock_send_email.call_args_list[0].kwargs
        self.assertEqual(send_email_kwargs['personalisation']['username'], self.user.username)
        self.assertNotIn(self.current_password, send_email_kwargs['personalisation'].values())
        password = send_email_kwargs['personalisation']['password']
        user = authenticate(username=self.user.username, password=password)
        self.assertEqual(self.user.username, getattr(user, 'username', None),
                         msg='Cannot log in with new password')

    def test_password_reset_by_username(self, mock_send_email):
        self.assertPasswordReset(mock_send_email, self.user.username)

    def test_password_reset_by_username_case_insensitive(self, mock_send_email):
        self.assertPasswordReset(mock_send_email, self.user.username.swapcase())

    def test_password_reset_by_email(self, mock_send_email):
        self.assertPasswordReset(mock_send_email, self.user.email)

    def test_password_reset_by_email_case_insensitive(self, mock_send_email):
        self.assertPasswordReset(mock_send_email, self.user.email.title())

    def test_create_password_change_request(self, mock_send_email):
        response = self.client.post(self.reset_url, {
            'username': self.user.username,
            'create_password': {
                'password_change_url': 'http://localhost/path',
                'reset_code_param': 'reset_code'
            }
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        user = authenticate(username=self.user.username, password=self.current_password)
        self.assertEqual(self.user.username, getattr(user, 'username', None),
                         msg='Cannot log in with old password')

        self.assertEqual(PasswordChangeRequest.objects.all().count(), 1)
        self.assertEqual(mock_send_email.call_count, 1)
        change_request = PasswordChangeRequest.objects.all().first()
        self.assertEqual(
            mock_send_email.call_args_list[0].kwargs['personalisation']['change_password_url'],
            f'http://localhost/path?reset_code={change_request.code}',
        )


class ChangePasswordWithCodeTestCase(AuthBaseTestCase):
    reset_url = reverse_lazy('user-reset-password')

    def setUp(self):
        super().setUp()
        self.user = make_test_users()['prison_clerks'][0]
        self.current_password = 'Password321='
        self.user.set_password(self.current_password)
        self.user.save()
        self.new_password = 'django2point2insistsyouhaveastrongpasswordsohereitis'
        self.incorrect_code = '55d5ff5d-598e-48a8-b68e-54f22c32c472'

    def get_change_url(self, code):
        return reverse_lazy('user-change-password-with-code', kwargs={'code': code})

    @mock.patch('mtp_auth.views.send_email')
    def test_password_change_with_code(self, mock_send_email):
        response = self.client.post(self.reset_url, {
            'username': self.user.username,
            'create_password': {
                'password_change_url': 'http://localhost/',
                'reset_code_param': 'reset_code'
            }
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(mock_send_email.call_count, 1)

        code = PasswordChangeRequest.objects.all().first().code
        response = self.client.post(
            self.get_change_url(code), {'new_password': self.new_password}
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        user = authenticate(username=self.user.username, password=self.current_password)
        self.assertIsNone(user, msg='Password was not changed')

        user = authenticate(username=self.user.username, password=self.new_password)
        self.assertEqual(self.user.username, getattr(user, 'username', None),
                         msg='Cannot log in with new password')

    @mock.patch('mtp_auth.views.send_email')
    def test_password_change_fails_with_incorrect_code(self, mock_send_email):
        self.client.post(self.reset_url, {
            'username': self.user.username,
            'create_password': {
                'password_change_url': 'http://localhost/',
                'reset_code_param': 'reset_code'
            }
        }, format='json')
        response = self.client.post(
            self.get_change_url(self.incorrect_code),
            {'new_password': self.new_password}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(mock_send_email.call_count, 1)

        user = authenticate(username=self.user.username, password=self.current_password)
        self.assertEqual(self.user.username, getattr(user, 'username', None),
                         msg='Cannot log in with old password')


@mock.patch(
    'mtp_auth.permissions.AccountRequestPermissions',
    (CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID)
)
class AccountRequestTestCase(AuthBaseTestCase):
    url_detail = reverse_lazy('accountrequest-detail')

    def setUp(self):
        super().setUp()
        self.users = make_test_users(clerks_per_prison=1)
        self.users.update(make_test_user_admins())

    def test_create_requests(self):
        url_list = reverse('accountrequest-list')
        valid = [
            {
                'first_name': 'Mark', 'last_name': 'Smith',
                'email': 'm@mtp.local', 'username': 'abc123',
                'role': 'prison-clerk', 'prison': 'IXB',
            },
            {
                'first_name': 'Mark', 'last_name': 'Smith',
                'email': 'm@mtp.local', 'username': 'abc123',
                'role': 'security', 'manager_email': 'my.manager@mtp.local',
                'reason': 'abc',
            },
        ]
        for item in valid:
            response = self.client.post(url_list, data=item, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.content)
            response_data = response.json()
            self.assertDictEqual(item, {
                key: value
                for key, value in response_data.items()
                if key in item
            })
        self.assertEqual(AccountRequest.objects.count(), len(valid))

    def test_invalid_creation_requests(self):
        url_list = reverse('accountrequest-list')
        invalid = [
            # no data
            None,
            # incorrect app
            {
                'first_name': 'Mark', 'last_name': 'Smith',
                'email': 'm@mtp.local', 'username': 'abc123',
                'role': '~nonexistant', 'prison': 'IXB',
            },
            # missing text
            {
                'first_name': 'Mark', 'last_name': '',
                'email': 'm@mtp.local', 'username': 'abc123',
                'role': 'prison-clerk', 'prison': 'IXB',
            },
            # invalid email
            {
                'first_name': 'Mark', 'last_name': 'Smith',
                'email': 'mark', 'username': 'abc123',
                'role': 'prison-clerk', 'prison': 'IXB',
            },
            # missing prison
            {
                'first_name': 'Mark', 'last_name': 'Smith',
                'email': 'm@mtp.local', 'username': 'abc123',
                'role': 'prison-clerk', 'prison': None,
            },
            # app by pk not client_id
            {
                'first_name': 'Mark', 'last_name': 'Smith',
                'email': 'm@mtp.local', 'username': 'abc123',
                'role': Role.objects.first().pk, 'prison': 'IXB',
            },
            # for 'security' role manager's email is required
            {
                'first_name': 'Mark', 'last_name': 'Smith',
                'email': 'm@mtp.local', 'username': 'UniqueID12345',
                'role': 'security', 'prison': 'IXB',
                'manager_email': '',
            },
        ]
        for item in invalid:
            response = self.client.post(url_list, data=item, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=response.content)
        self.assertFalse(AccountRequest.objects.exists())

    def test_cannot_create_if_authenticated(self):
        url_list = reverse('accountrequest-list')
        user = self.users['prison_clerks'][0]
        response = self.client.post(url_list, data={
            'first_name': 'Mark', 'last_name': 'Smith',
            'email': 'm@mtp.local', 'username': 'abc123',
            'role': 'prison-clerk', 'prison': 'IXB',
        }, format='json', HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=response.content)
        self.assertFalse(AccountRequest.objects.exists())

    def test_cannot_create_with_same_role_and_username(self):
        url_list = reverse('accountrequest-list')
        response = self.client.post(url_list, data={
            'first_name': 'Mark', 'last_name': 'Smith',
            'email': 'mark@mtp.local', 'username': 'abc123',
            'role': 'prison-clerk', 'prison': 'IXB',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.content)
        response = self.client.post(url_list, data={
            'first_name': 'Mary', 'last_name': 'Johns',
            'email': 'mary@mtp.local', 'username': 'abc123',
            'role': 'prison-clerk', 'prison': 'INP',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=response.content)
        self.assertEqual(AccountRequest.objects.count(), 1)
        response = self.client.post(url_list, data={
            'first_name': 'Mary', 'last_name': 'Johns',
            'email': 'mary@mtp.local', 'username': 'abc123',
            'role': 'security', 'prison': 'INP', 'manager_email': 'my.manager@mtp.local',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.content)
        self.assertEqual(AccountRequest.objects.count(), 2)

    def test_cannot_create_for_existing_user_if_not_confirmed(self):
        url_list = reverse('accountrequest-list')
        user = basic_user.make(username='abc123')
        role = Role.objects.get(name='security')
        role.assign_to_user(user)

        response = self.client.post(url_list, data={
            'first_name': 'Mary', 'last_name': 'Johns',
            'email': 'mary@mtp.local', 'username': 'abc123',
            'role': 'prison-clerk', 'prison': 'INP',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=response.content)
        response_data = response.json()
        self.assertDictEqual(response_data['__mtp__'], {
            'condition': 'user-exists',
            'roles': [{'role': role.name, 'application': role.application.name, 'login_url': role.login_url}]
        })
        self.assertFalse(AccountRequest.objects.exists())

        response = self.client.post(url_list, data={
            'first_name': 'Mary', 'last_name': 'Johns',
            'email': 'mary@mtp.local', 'username': 'abc123',
            'role': 'prison-clerk', 'prison': 'INP',
            'change-role': 'True',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.content)
        self.assertEqual(AccountRequest.objects.count(), 1)

    def test_create_for_existing_user_without_roles_without_confirmation(self):
        url_list = reverse('accountrequest-list')
        basic_user.make(username='abc123')
        response = self.client.post(url_list, data={
            'first_name': 'Mary', 'last_name': 'Johns',
            'email': 'mary@mtp.local', 'username': 'abc123',
            'role': 'prison-clerk', 'prison': 'INP',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.content)
        self.assertEqual(AccountRequest.objects.count(), 1)

    def test_cannot_create_for_existing_superuser(self):
        url_list = reverse('accountrequest-list')
        basic_user.make(username='abc123', is_superuser=True)
        response = self.client.post(url_list, data={
            'first_name': 'Mary', 'last_name': 'Johns',
            'email': 'mary@mtp.local', 'username': 'abc123',
            'role': 'prison-clerk', 'prison': 'INP',
            'change-role': 'True',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=response.content)
        self.assertFalse(AccountRequest.objects.exists())

    def test_creating_for_existing_user_copies_user_fields(self):
        url_list = reverse('accountrequest-list')
        copied_fields = {
            'first_name': 'Mark', 'last_name': 'Smith',
            'email': 'mark@mtp.local', 'username': 'abc123',
        }
        basic_user.make(**copied_fields)
        response = self.client.post(url_list, data={
            'first_name': 'Mary', 'last_name': 'Johns',
            'email': 'mary@mtp.local', 'username': 'abc123',
            'role': 'prison-clerk', 'prison': 'INP',
            'change-role': 'True',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.content)
        response_data = response.json()
        self.assertDictEqual(copied_fields, {
            key: value
            for key, value in response_data.items()
            if key in copied_fields
        })
        self.assertEqual(AccountRequest.objects.count(), 1)

    def test_authentication_required(self):
        url_list = reverse('accountrequest-list')
        for method in ('put', 'patch', 'delete'):  # post allowed, get returns only count
            response = getattr(self.client, method)(url_list)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            response = self.client.get(url_list)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(list(response.json().keys()), ['count'])

        AccountRequest.objects.create(
            first_name='Mark', last_name='Smith',
            email='m@mtp.local', username='abc123',
            role=Role.objects.get(name='prison-clerk'),
            prison=Prison.objects.get(nomis_id='IXB'),
        )
        url_detail = reverse('accountrequest-detail', kwargs={'pk': AccountRequest.objects.last().pk})
        for method in ('get', 'post', 'put', 'patch', 'delete'):
            response = getattr(self.client, method)(url_detail)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_admin_required(self):
        user = self.users['prison_clerks'][0]
        AccountRequest.objects.create(
            first_name='Mark', last_name='Smith',
            email='m@mtp.local', username='abc123',
            role=Role.objects.get(name='prison-clerk'),
            prison=Prison.objects.get(nomis_id='IXB'),
        )
        url_list = reverse('accountrequest-list')
        url_detail = reverse('accountrequest-detail', kwargs={'pk': AccountRequest.objects.last().pk})

        response = self.client.get(
            url_list,
            format='json', HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=response.content)
        response = self.client.get(
            url_detail,
            format='json', HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=response.content)

    def test_only_supported_apps(self):
        admin = self.users['bank_admin_uas'][0]
        url_list = reverse('accountrequest-list')
        response = self.client.get(
            url_list,
            format='json', HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=response.content)

    def test_list_requests(self):
        admin = self.users['prison_clerk_uas'][0]
        prison = admin.prisonusermapping.prisons.first()
        url_list = reverse('accountrequest-list')

        response = self.client.get(
            url_list,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        response_data = response.json()
        self.assertEqual(response_data['count'], 0)

        AccountRequest.objects.create(
            first_name='Mark', last_name='Smith',
            email='m123@mtp.local', username='abc123',
            role=Role.objects.get(name='prison-clerk'),
            prison=prison,
        )
        response = self.client.get(
            url_list,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        response_data = response.json()
        self.assertEqual(response_data['count'], 1)
        self.assertEqual(response_data['results'][0]['email'], 'm123@mtp.local')

    def test_request_details(self):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        request = mommy.make(AccountRequest, role=role, prison=prison)
        url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
        response = self.client.get(
            url_detail,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        response_data = response.json()
        for key in ('first_name', 'last_name', 'email', 'username', 'reason'):
            self.assertEqual(getattr(request, key), response_data[key])
        self.assertEqual(request.role.name, response_data['role'])
        self.assertEqual(request.prison.nomis_id, response_data['prison'])

    def test_cannot_list_other_roles(self):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        url_list = reverse('accountrequest-list')

        visible_requests = mommy.make(AccountRequest, 3, role=role, prison=prison)
        invisible_requests = []
        for another_role in Role.objects.exclude(name='prison-clerk'):
            invisible_requests.append(mommy.make(AccountRequest, role=another_role, prison=prison))

        response = self.client.get(
            url_list,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        response_data = response.json()
        self.assertEqual(response_data['count'], 3)
        self.assertTrue(all(
            result['role'] == 'prison-clerk'
            for result in response_data['results']
        ))

        url_detail = reverse('accountrequest-detail', kwargs={'pk': random.choice(visible_requests).pk})
        response = self.client.get(
            url_detail,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        response_data = response.json()
        self.assertEqual(response_data['role'], 'prison-clerk')

        for invisible_request in invisible_requests:
            url_detail = reverse('accountrequest-detail', kwargs={'pk': invisible_request.pk})
            with silence_logger('django.request', level=logging.ERROR):
                response = self.client.get(
                    url_detail,
                    format='json',
                    HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
                )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content)

    def test_cannot_list_from_different_application(self):
        admin = self.users['prison_clerk_uas'][0]
        cashbook_role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        Role.objects.get(name='bank-admin').assign_to_user(admin)
        url_list = reverse('accountrequest-list')

        mommy.make(AccountRequest, 3, role=cashbook_role, prison=prison)
        response = self.client.get(
            url_list,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=BANK_ADMIN_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=response.content)

    def test_cannot_list_other_prisons(self):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        url_list = reverse('accountrequest-list')

        another_prison = Prison.objects.exclude(nomis_id=prison.nomis_id).first()
        visible_requests = mommy.make(AccountRequest, 3, role=role, prison=prison)
        invisible_requests = mommy.make(AccountRequest, 5, role=role, prison=another_prison)

        response = self.client.get(
            url_list,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        response_data = response.json()
        self.assertEqual(response_data['count'], 3)
        self.assertTrue(all(
            result['prison'] == prison.nomis_id
            for result in response_data['results']
        ))

        url_detail = reverse('accountrequest-detail', kwargs={'pk': random.choice(visible_requests).pk})
        response = self.client.get(
            url_detail,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        response_data = response.json()
        self.assertEqual(response_data['prison'], prison.nomis_id)

        url_detail = reverse('accountrequest-detail', kwargs={'pk': random.choice(invisible_requests).pk})
        with silence_logger('django.request', level=logging.ERROR):
            response = self.client.get(
                url_detail,
                format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
            )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content)

    @mock.patch('mtp_auth.views.send_email')
    def test_decline_requests(self, mock_send_email):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        user_count = User.objects.count()

        request = AccountRequest.objects.create(
            first_name='Mark', last_name='Smith',
            email='mark@example.com', username='abc123',
            role=role, prison=prison,
        )
        url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
        response = self.client.delete(
            url_detail,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, msg=response.content)

        self.assertEqual(mock_send_email.call_count, 1)
        send_email_kwargs = mock_send_email.call_args_list[0].kwargs
        self.assertEqual(send_email_kwargs['template_name'], 'api-account-request-denied')
        self.assertEqual(send_email_kwargs['to'], 'mark@example.com')
        self.assertEqual(send_email_kwargs['personalisation']['service_name'], role.application.name.lower())

        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count)

    @mock.patch('mtp_auth.serializers.send_email')
    def test_confirm_new_requests(self, mock_send_email):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        user_count = User.objects.count()

        def assert_user_created(payload, user_admin):
            request = mommy.make(AccountRequest, role=role, prison=prison)
            url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
            response = self.client.patch(
                url_detail,
                data=payload,
                format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)

            user = User.objects.get(username=request.username)
            for key in ('first_name', 'last_name', 'email'):
                self.assertEqual(getattr(user, key), getattr(request, key))
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
            self.assertIs(user.groups.filter(name='UserAdmin').exists(), user_admin)
            self.assertSequenceEqual(
                user.prisonusermapping.prisons.values_list('nomis_id', flat=True),
                [prison.nomis_id]
            )

            send_email_kwargs = mock_send_email.call_args_list[-1].kwargs
            self.assertEqual(send_email_kwargs['template_name'], 'api-new-user')
            self.assertEqual(send_email_kwargs['to'], request.email)
            self.assertEqual(send_email_kwargs['personalisation']['username'], user.username)
            self.assertEqual(send_email_kwargs['personalisation']['service_name'], role.application.name.lower())
            self.assertEqual(send_email_kwargs['personalisation']['login_url'], role.login_url)
            password = send_email_kwargs['personalisation']['password']
            self.assertTrue(user.check_password(password))

        assert_user_created({}, user_admin=False)
        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + 1)

        assert_user_created({'user_admin': 'true'}, user_admin=True)
        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + 2)

    @mock.patch('mtp_auth.serializers.send_email')
    def test_confirm_new_requests_with_multiple_prisons(self, mock_send_email):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        PrisonUserMapping.objects.assign_prisons_to_user(admin, Prison.objects.all())
        user_count = User.objects.count()

        request = mommy.make(AccountRequest, role=role, prison=prison)
        url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
        response = self.client.patch(
            url_detail,
            data={},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        self.assertEqual(mock_send_email.call_count, 1)
        self.assertEqual(mock_send_email.call_args_list[-1].kwargs['template_name'], 'api-new-user')

        user = User.objects.get(username=request.username)
        self.assertSetEqual(
            set(user.prisonusermapping.prisons.values_list('nomis_id', flat=True)),
            set(Prison.objects.values_list('nomis_id', flat=True)),
            msg='User should get all prisons, not just requested one'
        )

        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + 1)

    @mock.patch('mtp_auth.views.send_email')
    def test_confirm_requests_with_existing_user(self, mock_send_email):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        user_count = User.objects.count()

        # all variations move to above role and prison
        another_role = 'security'
        another_prison = Prison.objects.exclude(nomis_id=prison.nomis_id).first().nomis_id
        scenarios = [
            {
                'scenario': 'no previous role',
                'previous_role': None, 'previous_prisons': [],
                'previous_extra_groups': [],
                'user_admin': False,
            },
            {
                'scenario': 'role change',
                'previous_role': another_role, 'previous_prisons': [prison.nomis_id],
                'previous_extra_groups': [],
                'user_admin': False,
            },
            {
                'scenario': 'prison change',
                'previous_role': role.name, 'previous_prisons': [another_prison],
                'previous_extra_groups': [],
                'user_admin': False,
            },
            {
                'scenario': 'one prison removed',
                'previous_role': role.name, 'previous_prisons': [prison.nomis_id, another_prison],
                'previous_extra_groups': [],
                'user_admin': False,
            },
            {
                'scenario': 'no prison before',
                'previous_role': role.name, 'previous_prisons': [],
                'previous_extra_groups': [],
                'user_admin': False,
            },
            {
                'scenario': 'prison and role change',
                'previous_role': another_role, 'previous_prisons': [another_prison],
                'previous_extra_groups': [],
                'user_admin': False,
            },
            {
                'scenario': 'prison and role and group change',
                'previous_role': another_role, 'previous_prisons': [another_prison],
                'previous_extra_groups': ['BankAdmin'],
                'user_admin': False,
            },
            {
                'scenario': 'prison and role and admin change',
                'previous_role': another_role, 'previous_prisons': [another_prison],
                'previous_extra_groups': [],
                'user_admin': True,
            },
            {
                'scenario': 'prison and role change and admin stays',
                'previous_role': another_role, 'previous_prisons': [another_prison],
                'previous_extra_groups': ['BankAdmin', 'UserAdmin'],
                'user_admin': True,
            },
            {
                'scenario': 'prison and role change and admin removed',
                'previous_role': another_role, 'previous_prisons': [another_prison],
                'previous_extra_groups': ['UserAdmin'],
                'user_admin': False,
            },
        ]
        for scenarion_num, scenario in enumerate(scenarios):
            user = basic_user.make(is_active=random.random() > 0.2)
            if scenario['previous_role']:
                Role.objects.get(name=scenario['previous_role']).assign_to_user(user)
            if scenario['previous_prisons']:
                PrisonUserMapping.objects.create(user=user).prisons.set([
                    Prison.objects.get(nomis_id=p)
                    for p in scenario['previous_prisons']
                ])
            for group in scenario['previous_extra_groups']:
                user.groups.add(Group.objects.get(name=group))

            request = mommy.make(
                AccountRequest,
                first_name=user.first_name, last_name=user.last_name,
                email=user.email, username=user.username,
                role=role, prison=prison,
            )
            url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
            response = self.client.patch(
                url_detail,
                data={'user_admin': 'true' if scenario['user_admin'] else 'false'},
                format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)

            refreshed_user = User.objects.get(username=user.username)
            for key in ('first_name', 'last_name', 'email'):
                self.assertEqual(getattr(refreshed_user, key), getattr(user, key))
            self.assertFalse(refreshed_user.is_superuser)
            self.assertTrue(refreshed_user.is_active)
            self.assertEqual(refreshed_user.is_staff, user.is_staff)
            self.assertIs(refreshed_user.groups.filter(name='UserAdmin').exists(), scenario['user_admin'])
            if scenario['previous_extra_groups']:
                self.assertFalse(any(
                    refreshed_user.groups.filter(name=group).exists()
                    for group in scenario['previous_extra_groups']
                    if group != 'UserAdmin'
                ))
            self.assertSequenceEqual(
                refreshed_user.prisonusermapping.prisons.values_list('nomis_id', flat=True),
                [prison.nomis_id]
            )

            self.assertEqual(mock_send_email.call_count, scenarion_num + 1)
            send_email_kwargs = mock_send_email.call_args_list[-1].kwargs
            self.assertEqual(send_email_kwargs['to'], request.email)
            self.assertEqual(send_email_kwargs['personalisation']['username'], refreshed_user.username)
            self.assertEqual(send_email_kwargs['personalisation']['service_name'], role.application.name.lower())
            self.assertEqual(send_email_kwargs['personalisation']['login_url'], role.login_url)
            self.assertNotIn('password', send_email_kwargs['personalisation'])

        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + len(scenarios))

    @mock.patch('mtp_auth.views.send_email')
    def test_confirm_requests_with_existing_user_with_multiple_prisons(self, mock_send_email):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        PrisonUserMapping.objects.assign_prisons_to_user(admin, Prison.objects.all())
        user_count = User.objects.count()

        user = basic_user.make(is_active=random.random() > 0.2)
        Role.objects.get(name='security').assign_to_user(user)
        request = mommy.make(
            AccountRequest,
            first_name=user.first_name, last_name=user.last_name,
            email=user.email, username=user.username,
            role=role, prison=prison,
        )
        url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
        response = self.client.patch(
            url_detail,
            data={},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        self.assertEqual(mock_send_email.call_count, 1)
        self.assertEqual(mock_send_email.call_args_list[-1].kwargs['template_name'], 'api-user-moved')

        user = User.objects.get(username=request.username)
        self.assertSetEqual(
            set(user.prisonusermapping.prisons.values_list('nomis_id', flat=True)),
            set(Prison.objects.values_list('nomis_id', flat=True)),
            msg='User should get all prisons, not just requested one'
        )

        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + 1)

    def test_cannot_confirm_superadmin_change(self):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()

        # security user in same prison with superadmin flag
        user = basic_user.make(is_superuser=True)
        previous_email = user.email
        Role.objects.get(name='security').assign_to_user(user)
        PrisonUserMapping.objects.create(user=user).prisons.set([prison])

        # request to move to cashbook in same prison, change email and make user admin
        request = mommy.make(
            AccountRequest,
            first_name=user.first_name, last_name=user.last_name,
            username=user.username,
            role=role, prison=prison,
        )
        url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
        response = self.client.patch(
            url_detail,
            data={'user_admin': 'true'},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=response.content)
        self.assertIn('Super users cannot be edited', response.content.decode())

        self.assertEqual(user.email, previous_email)
        self.assertSequenceEqual(
            user.groups.values_list('name', flat=True),
            ['Security']
        )
        self.assertSequenceEqual(
            user.prisonusermapping.prisons.values_list('nomis_id', flat=True),
            [prison.nomis_id]
        )

    def test_cannot_confirm_self_change(self):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()

        user = admin
        previous_email = user.email

        # request to move to cashbook in same prison, change email and make user admin
        request = mommy.make(
            AccountRequest,
            first_name=user.first_name, last_name=user.last_name,
            username=user.username,
            role=role, prison=prison,
        )
        url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
        response = self.client.patch(
            url_detail,
            data={'user_admin': 'true'},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=response.content)
        self.assertIn('You cannot confirm changes to yourself', response.content.decode())

        self.assertEqual(user.email, previous_email)
        self.assertSequenceEqual(
            user.groups.values_list('name', flat=True),
            ['PrisonClerk', 'UserAdmin']
        )
        self.assertSequenceEqual(
            user.prisonusermapping.prisons.values_list('nomis_id', flat=True),
            [prison.nomis_id]
        )

    def test_cannot_action_unowned_requests(self):
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        user_count = User.objects.count()

        another_role = Role.objects.exclude(name='prison-clerk').first()
        self.assertNotIn(another_role, Role.objects.get_roles_for_user(admin))
        another_prison = Prison.objects.exclude(nomis_id=prison.nomis_id).first()
        invisible_requests = [
            mommy.make(AccountRequest, role=role, prison=another_prison),
            mommy.make(AccountRequest, role=another_role, prison=prison),
        ]
        for request in invisible_requests:
            url_detail = reverse('accountrequest-detail', kwargs={'pk': request.pk})
            with silence_logger('django.request', level=logging.ERROR):
                response = self.client.delete(
                    url_detail,
                    format='json',
                    HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
                )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content)
            with silence_logger('django.request', level=logging.ERROR):
                response = self.client.patch(
                    url_detail,
                    data={'user_admin': 'true'},
                    format='json',
                    HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=CASHBOOK_OAUTH_CLIENT_ID)
                )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, msg=response.content)

        self.assertEqual(AccountRequest.objects.count(), 2)
        self.assertEqual(User.objects.count(), user_count)

    def test_unauthenticated_user_filters_for_username(self):
        # Setup
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        PrisonUserMapping.objects.assign_prisons_to_user(admin, Prison.objects.all())

        user = basic_user.make(is_active=True)
        role.assign_to_user(user)
        mommy.make(
            AccountRequest,
            first_name=user.first_name, last_name=user.last_name,
            email=user.email, username=user.username,
            role=role, prison=prison,
        )
        self.assertEqual(AccountRequest.objects.count(), 1)

        # Execute
        response = self.client.get(
            '{}?{}'.format(
                reverse('accountrequest-list'),
                urlencode([('username', user.username), ('role__name', role.name)]),
            ),
            format='json'
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        self.assertEqual(
            response.json(),
            {
                'count': 1
            }
        )

    def test_unauthenticated_filtering_different_user(self):
        # Setup
        admin = self.users['prison_clerk_uas'][0]
        role = Role.objects.get(name='prison-clerk')
        prison = admin.prisonusermapping.prisons.first()
        PrisonUserMapping.objects.assign_prisons_to_user(admin, Prison.objects.all())

        user = basic_user.make(is_active=True)
        role.assign_to_user(user)
        mommy.make(
            AccountRequest,
            first_name=user.first_name, last_name=user.last_name,
            email=user.email, username=user.username,
            role=role, prison=prison,
        )
        self.assertEqual(AccountRequest.objects.count(), 1)

        # Execute
        response = self.client.get(
            '{}?{}'.format(
                reverse('accountrequest-list'),
                urlencode([('username', 'some_other_username'), ('role__name', role.name)]),
            ),
            format='json'
        )

        # Assert
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.content)
        self.assertEqual(
            response.json(),
            {
                'count': 0
            }
        )
