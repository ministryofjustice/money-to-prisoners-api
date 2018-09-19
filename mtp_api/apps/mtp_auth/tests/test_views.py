import base64
import datetime
import json
import logging
import random
import re
from unittest import mock

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse, reverse_lazy
from django.test import override_settings
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
    PrisonUserMapping, Role,
    Login, FailedLoginAttempt,
    PasswordChangeRequest, AccountRequest,
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


class AuthBaseTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = [
        'initial_groups.json',
        'initial_types.json',
        'test_prisons.json',
    ]

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
        self.security_uas = test_uas['security_staff_uas']
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

    def test_bank_admin_user_manages_only_self(self):
        user = random.choice(self.bank_uas)
        self.assertCanListRoles(user, ['bank-admin'], self.url + '?managed')

    def test_pla_user_manages_only_self(self):
        user = random.choice(self.pla_uas)
        self.assertCanListRoles(user, ['prisoner-location-admin'], self.url + '?managed')

    def test_cashbook_user_manages_security_too(self):
        user = random.choice(self.cashbook_uas)
        self.assertCanListRoles(user, ['prison-clerk', 'security'], self.url + '?managed')

    def test_security_user_manages_cashbook_too(self):
        user = random.choice(self.security_uas)
        self.assertCanListRoles(user, ['prison-clerk', 'security'], self.url + '?managed')


class GetUserTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=2)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.send_money_users = test_users['send_money_users']
        self.test_users = (
            self.prison_clerks + self.prisoner_location_admins +
            self.bank_admins + self.refund_bank_admins
        )
        self.bank_uas = make_test_user_admins()['bank_admin_uas']

        self.prisons = Prison.objects.all()

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
                 ['prisoner-location-admin'], [], ['bank-admin']]
        for user, roles in zip(self.test_users, roles):
            url = self._get_url(user.username)
            response = self.client.get(
                url, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            self.assertListEqual(response.data['roles'], roles)

    def test_all_valid_usernames_retrievable(self):
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
        response = self.client.get(
            self._get_url(username),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.bank_uas[0])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], username)


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
        self.security_uas = test_uas['security_staff_uas']

    def get_url(self):
        return reverse('user-list')

    def test_list_users_only_accessible_to_admins(self):
        response = self.client.get(
            self.get_url(),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.refund_bank_admins[0])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def assertCanListUsers(self, requester, allowed_client_ids, exact_prison_match=True):  # noqa: N802
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
            if exact_prison_match:
                self.assertSamePrisons(requester, user,
                                       msg='User Admin able to retrieve users without matching prisons')
            else:
                self.assertSubsetPrisons(requester, user,
                                         msg='User Admin able to retrieve users without matching prisons')
        return response.data['results']

    def test_list_users_in_same_role(self):
        self.assertCanListUsers(self.bank_uas[0], {'bank-admin'})
        self.assertCanListUsers(self.pla_uas[0], {'noms-ops'})
        self.assertCanListUsers(self.security_uas[0], {'noms-ops'})

    def test_list_users_in_same_prison(self):
        users = self.assertCanListUsers(self.cashbook_uas[0], {'cashbook', 'noms-ops'})
        self.assertIn(self.security_uas[1].username, (user['username'] for user in users))

        users = self.assertCanListUsers(self.security_uas[1], {'cashbook', 'noms-ops'})
        self.assertIn(self.cashbook_uas[0].username, (user['username'] for user in users))

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


class CreateUserTestCase(AuthBaseTestCase):
    def setUp(self):
        super().setUp()
        test_uas = make_test_user_admins()
        self.cashbook_uas = test_uas['prison_clerk_uas']
        self.pla_uas = test_uas['prisoner_location_uas']
        self.bank_uas = test_uas['bank_admin_uas']
        self.security_uas = test_uas['security_staff_uas']

    def get_url(self):
        return reverse('user-list')

    def test_normal_user_cannot_create_user(self):
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

    @override_settings(ENVIRONMENT='prod')
    def assertUserCreated(self, requester, user_data, client_id, groups,  # noqa: N802
                          target_client_id=None, expected_login_link=None):
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
        self.assertSamePrisons(requester, new_user, msg='User Admin able to retrieve users without matching prisons')

        if make_user_admin:
            self.assertIn('UserAdmin', new_user.groups.values_list('name', flat=True))
        else:
            self.assertNotIn('UserAdmin', new_user.groups.values_list('name', flat=True))

        latest_email = mail.outbox[-1]
        self.assertIn(user_data['username'], latest_email.body)
        if expected_login_link:
            self.assertIn('sign in at', latest_email.body)
            self.assertIn(expected_login_link, latest_email.body)
        else:
            self.assertNotIn('sign in at', latest_email.body)
        self.assertEqual(
            'Your new %s account is ready to use' % Application.objects.get(client_id=target_client_id).name.lower(),
            latest_email.subject
        )

    def test_create_bank_admin(self):
        user_data = {
            'username': 'new-bank-admin',
            'first_name': 'New',
            'last_name': 'Bank Admin',
            'email': 'nba@mtp.local',
            'role': 'bank-admin',
        }
        self.assertUserCreated(
            self.bank_uas[0],
            user_data,
            'bank-admin',
            [Group.objects.get(name='BankAdmin'),
             Group.objects.get(name='RefundBankAdmin')]
        )

    def test_create_prisoner_location_admin(self):
        user_data = {
            'username': 'new-location-admin',
            'first_name': 'New',
            'last_name': 'Location Admin',
            'email': 'nla@mtp.local',
            'role': 'prisoner-location-admin',
        }
        self.assertUserCreated(
            self.pla_uas[0],
            user_data,
            'noms-ops',
            [Group.objects.get(name='PrisonerLocationAdmin')]
        )

    def test_create_security_staff(self):
        user_data = {
            'username': 'new-security-staff',
            'first_name': 'New',
            'last_name': 'Security Staff',
            'email': 'nss@mtp.local',
            'role': 'security',
        }
        self.assertUserCreated(
            self.security_uas[0],
            user_data,
            'noms-ops',
            [Group.objects.get(name='Security')]
        )

    def test_create_security_staff_as_prison_clerk(self):
        user_data = {
            'username': 'new-security-staff',
            'first_name': 'New',
            'last_name': 'Security Staff',
            'email': 'nss@mtp.local',
            'role': 'security',
        }
        self.assertUserCreated(
            self.cashbook_uas[0],
            user_data,
            'cashbook',
            [Group.objects.get(name='Security')],
            target_client_id='noms-ops',
        )

    def test_create_prison_clerk(self):
        user_data = {
            'username': 'new-prison-clerk',
            'first_name': 'New',
            'last_name': 'Prison Clerk',
            'email': 'pc@mtp.local',
            'role': 'prison-clerk',
        }
        self.assertUserCreated(
            self.cashbook_uas[0],
            user_data,
            'cashbook',
            [Group.objects.get(name='PrisonClerk')]
        )

    def test_create_prison_clerk_as_security(self):
        user_data = {
            'username': 'new-prison-clerk',
            'first_name': 'New',
            'last_name': 'Prison Clerk',
            'email': 'pc@mtp.local',
            'role': 'prison-clerk',
        }
        self.assertUserCreated(
            self.security_uas[0],
            user_data,
            'noms-ops',
            [Group.objects.get(name='PrisonClerk')],
            target_client_id='cashbook'
        )

    def test_create_cashbook_user_admin(self):
        user_data = {
            'username': 'new-cashbook-ua',
            'first_name': 'New',
            'last_name': 'Cashbook User Admin',
            'email': 'cua@mtp.local',
            'user_admin': True,
            'role': 'prison-clerk',
        }
        self.assertUserCreated(
            self.cashbook_uas[0],
            user_data,
            'cashbook',
            [Group.objects.get(name='PrisonClerk'),
             Group.objects.get(name='UserAdmin')]
        )

    def test_login_link_present(self):
        Role.objects.filter(name='prison-clerk').update(login_url='https://cashbook.local/login/')
        user_data = {
            'username': 'new-prison-clerk',
            'first_name': 'New',
            'last_name': 'Prison Clerk',
            'email': 'pc@mtp.local',
            'role': 'prison-clerk',
        }
        self.assertUserCreated(
            self.cashbook_uas[0],
            user_data,
            'cashbook',
            [Group.objects.get(name='PrisonClerk')],
            expected_login_link='https://cashbook.local/login/',
        )

    def test_login_link_present_for_different_role(self):
        Role.objects.filter(name='security').update(login_url='https://noms-ops.local/login/')
        user_data = {
            'username': 'new-security-staff',
            'first_name': 'New',
            'last_name': 'Security Staff',
            'email': 'nss@mtp.local',
            'role': 'security',
        }
        self.assertUserCreated(
            self.cashbook_uas[0],
            user_data,
            'cashbook',
            [Group.objects.get(name='Security')],
            target_client_id='noms-ops',
            expected_login_link='https://noms-ops.local/login/',
        )

    def assertUserNotCreated(self, requester, data):  # noqa: N802
        response = self.client.post(
            self.get_url(),
            format='json',
            data=data,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(requester)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        return response

    def test_cannot_create_non_unique_username(self):
        user_data = {
            'username': self.cashbook_uas[0].username,
            'first_name': 'New',
            'last_name': 'Cashbook User Admin 2',
            'email': 'cua@mtp.local',
            'user_admin': True,
            'role': 'prison-clerk',
        }
        self.assertUserNotCreated(self.cashbook_uas[0], user_data)
        self.assertEqual(User.objects.filter(username=self.cashbook_uas[0].username).count(), 1)

    def test_username_case_sensitivity(self):
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

        username = 'a-user'
        user_data = {
            'username': username,
            'first_name': 'Lower',
            'last_name': 'Case',
            'email': 'lower-case@mtp.local',
            'role': 'prison-clerk',
        }
        response = self.assertUserNotCreated(requester, user_data)
        self.assertIn('username', response.json())
        self.assertEqual(User.objects.filter(username__exact=username).count(), 0)
        self.assertEqual(User.objects.filter(username__iexact=username).count(), 1)

    def test_cannot_create_non_unique_email(self):
        user_data = {
            'username': 'new-cashbook-ua',
            'first_name': 'New',
            'last_name': 'Cashbook User Admin',
            'email': self.cashbook_uas[0].email,
            'user_admin': True,
            'role': 'prison-clerk',
        }
        self.assertUserNotCreated(self.cashbook_uas[0], user_data)
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)

    def test_cannot_create_with_missing_fields(self):
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
            self.assertUserNotCreated(self.cashbook_uas[0], data)
            self.assertEqual(User.objects.filter(username=data['username']).count(), 0)

    def test_cannot_create_with_missing_role(self):
        user_data = {
            'username': 'new-user',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'user@mtp.local',
            'role': None,
        }
        response = self.assertUserNotCreated(self.cashbook_uas[0], user_data)
        self.assertIn('role', response.data)
        self.assertIn('Role must be specified', response.data['role'])
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)

    def test_cannot_create_with_unknown_role(self):
        user_data = {
            'username': 'new-user',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'user@mtp.local',
            'role': 'unknown',
        }
        response = self.assertUserNotCreated(self.cashbook_uas[0], user_data)
        self.assertIn('role', response.data)
        self.assertIn('Invalid role: unknown', response.data['role'])
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)

    def test_cannot_create_with_unmanaged_role(self):
        user_data = {
            'username': 'new-user',
            'first_name': 'New',
            'last_name': 'User',
            'email': 'user@mtp.local',
            'role': 'bank-admin',
        }
        response = self.assertUserNotCreated(self.cashbook_uas[0], user_data)
        self.assertIn('role', response.data)
        self.assertIn('Invalid role: bank-admin', response.data['role'])
        self.assertEqual(User.objects.filter(username=user_data['username']).count(), 0)


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
        self.security_uas = test_uas['security_staff_uas']

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
            'user_admin': True
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
            'user_admin': True
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
            'user_admin': False
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
            'user_admin': False
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
            'last_name': 'Name'
        }
        self.assertUserNotUpdated(
            self.refund_bank_admins[0],
            self.bank_admins[0].username,
            user_data
        )

    def test_update_self_as_normal_user_fails(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name'
        }
        self.assertUserNotUpdated(
            self.bank_admins[0],
            self.bank_admins[0].username,
            user_data
        )

    def test_update_prison_clerk_in_same_prison_succeeds(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name'
        }
        self.assertUserUpdated(
            self.cashbook_uas[0],
            self.prison_clerks[0].username,
            user_data
        )

    def test_update_prison_clerk_in_different_prison_fails(self):
        user_data = {
            'first_name': 'New',
            'last_name': 'Name'
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

    def test_can_change_role_in_own_app(self):
        user_data = {
            'role': 'security'
        }
        self.assertUserUpdated(
            self.cashbook_uas[0],
            self.prison_clerks[0].username,
            user_data
        )
        updated_user = User.objects.get(username=self.prison_clerks[0].username)
        groups = set(updated_user.groups.values_list('name', flat=True))
        self.assertNotIn('UserAdmin', groups)
        self.assertNotIn('PrisonClerk', groups)
        self.assertIn('Security', groups)

    def test_can_change_role_and_admin_level_in_own_app(self):
        user_data = {
            'role': 'security',
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
        self.assertNotIn('PrisonClerk', groups)
        self.assertIn('Security', groups)

    def test_can_change_role_in_own_prison_but_different_app(self):
        user_data = {
            'role': 'prison-clerk'
        }
        self.assertUserUpdated(
            self.cashbook_uas[0],
            self.security_users[1].username,
            user_data
        )
        updated_user = User.objects.get(username=self.security_users[1].username)
        groups = set(updated_user.groups.values_list('name', flat=True))
        self.assertNotIn('UserAdmin', groups)
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
        self.assertIn('Cannot change own access permissions', response.data)

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
        self.assertIn('PrisonClerk', updated_user.groups.values_list('name', flat=True))


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

    def test_user_deleting_self_fails(self):
        self.assertUserNotDeleted(
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

    def test_account_lockout_on_too_many_attempts(self):
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

    def test_account_lockout_on_too_many_attempts_without_case_sensitivity(self):
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
        prisoner_location_admin_client = Application.objects.get(client_id=NOMS_OPS_OAUTH_CLIENT_ID)

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

    @override_settings(ENVIRONMENT='prod')
    def test_email_sent_when_account_locked(self):
        prison_clerk = self.prison_clerks[0]
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT - 1):
            self.fail_login(prison_clerk, cashbook_client)
        self.assertEqual(len(mail.outbox), 0, msg='Email should not be sent')
        self.fail_login(prison_clerk, cashbook_client)
        self.assertEqual(len(mail.outbox), 1, msg='Email should be sent')
        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.fail_login(prison_clerk, cashbook_client)
        self.assertEqual(len(mail.outbox), 1, msg='Only one email should be sent')

        latest_email = mail.outbox[-1]
        self.assertIn(cashbook_client.name.lower(), latest_email.body)


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

    def test_account_lockout_on_too_many_attempts(self):
        cashbook_client = Application.objects.get(client_id=CASHBOOK_OAUTH_CLIENT_ID)

        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            self.assertFalse(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
            self.incorrect_password_attempt()

        self.assertTrue(FailedLoginAttempt.objects.is_locked_out(self.user, cashbook_client))
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


class ResetPasswordTestCase(AuthBaseTestCase):
    reset_url = reverse_lazy('user-reset-password')

    def setUp(self):
        super().setUp()
        self.user = make_test_users()['prison_clerks'][0]
        self.current_password = 'Password321='
        self.user.set_password(self.current_password)
        self.user.save()

    def assertErrorResponse(self, response, error_dict):  # noqa: N802
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

    def test_unknown_user(self):
        response = self.client.post(self.reset_url, {'username': 'unknown'})
        self.assertErrorResponse(response, {
            'username': [ResetPasswordView.error_messages['not_found']],
        })

    def test_incorrect_username(self):
        username = self.user.username
        if '-' in username:
            username = username.replace('-', '_')
        elif '_' in username:
            username = username.replace('_', '-')
        else:
            username += '_'
        response = self.client.post(self.reset_url, {'username': username})
        self.assertErrorResponse(response, {
            'username': [ResetPasswordView.error_messages['not_found']],
        })

    def test_unable_to_reset_immutable_user(self):
        username = 'send-money'
        try:
            User.objects.get(username=username)
        except User.DoesNotExist:
            self.fail()
        response = self.client.post(self.reset_url, {'username': username})
        self.assertErrorResponse(response, {
            'username': [ResetPasswordView.error_messages['not_found']],
        })

    def test_user_with_no_email(self):
        self.user.email = ''
        self.user.save()
        response = self.client.post(self.reset_url, {'username': self.user.username})
        self.assertErrorResponse(response, {
            'username': [ResetPasswordView.error_messages['no_email']],
        })

    def test_user_with_non_unique_email(self):
        other_user = User.objects.exclude(pk=self.user.pk).first()
        self.user.email = other_user.email.title()
        self.user.save()
        response = self.client.post(self.reset_url, {'username': self.user.email})
        self.assertErrorResponse(response, {
            'username': [ResetPasswordView.error_messages['multiple_found']],
        })

    def test_locked_user(self):
        app = Application.objects.first()
        for _ in range(settings.MTP_AUTH_LOCKOUT_COUNT):
            FailedLoginAttempt.objects.create(user=self.user, application=app)
        response = self.client.post(self.reset_url, {'username': self.user.username})
        self.assertErrorResponse(response, {
            'username': [ResetPasswordView.error_messages['locked_out']],
        })

    @override_settings(ENVIRONMENT='prod')
    def assertPasswordReset(self, username):  # noqa: N802
        response = self.client.post(self.reset_url, {'username': username})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        user = authenticate(username=self.user.username, password=self.current_password)
        self.assertIsNone(user, msg='Password was not changed')

        self.assertEqual(PasswordChangeRequest.objects.all().count(), 0,
                         msg='Password change request should not be created')

        latest_email = mail.outbox[-1]
        self.assertIn(self.user.username, latest_email.body)
        self.assertNotIn(self.current_password, latest_email.body)
        password_match = re.search(r'Password: (?P<password>[^\n]+)', latest_email.body)
        self.assertTrue(password_match, msg='Cannot find new password in email')
        user = authenticate(username=self.user.username,
                            password=password_match.group('password'))
        self.assertEqual(self.user.username, getattr(user, 'username', None),
                         msg='Cannot log in with new password')

    def test_password_reset_by_username(self):
        self.assertPasswordReset(self.user.username)

    def test_password_reset_by_username_case_insensitive(self):
        self.assertPasswordReset(self.user.username.swapcase())

    def test_password_reset_by_email(self):
        self.assertPasswordReset(self.user.email)

    def test_password_reset_by_email_case_insensitive(self):
        self.assertPasswordReset(self.user.email.title())

    @override_settings(ENVIRONMENT='prod')
    def test_create_password_change_request(self):
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
        self.assertEqual(len(mail.outbox), 1)
        change_request = PasswordChangeRequest.objects.all().first()
        self.assertTrue(
            'http://localhost/path?reset_code=%s' % str(change_request.code) in
            mail.outbox[-1].body
        )


class ChangePasswordWithCodeTestCase(AuthBaseTestCase):
    reset_url = reverse_lazy('user-reset-password')

    def setUp(self):
        super().setUp()
        self.user = make_test_users()['prison_clerks'][0]
        self.current_password = 'Password321='
        self.user.set_password(self.current_password)
        self.user.save()
        self.new_password = 'newpassword'
        self.incorrect_code = '55d5ff5d-598e-48a8-b68e-54f22c32c472'

    def get_change_url(self, code):
        return reverse_lazy('user-change-password-with-code', kwargs={'code': code})

    def test_password_change_with_code(self):
        response = self.client.post(self.reset_url, {
            'username': self.user.username,
            'create_password': {
                'password_change_url': 'http://localhost/',
                'reset_code_param': 'reset_code'
            }
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

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

    def test_password_change_fails_with_incorrect_code(self):
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

        user = authenticate(username=self.user.username, password=self.current_password)
        self.assertEqual(self.user.username, getattr(user, 'username', None),
                         msg='Cannot log in with old password')


@mock.patch(
    'mtp_auth.permissions.AccountRequestPremissions',
    (CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID)
)
class AccountRequestTestCase(AuthBaseTestCase):
    url_detail = reverse_lazy('accountrequest-detail')

    def setUp(self):
        super().setUp()
        self.users = make_test_users(clerks_per_prison=1)
        self.users.update(make_test_user_admins())
        for role in Role.objects.all():
            role.login_url = 'http://localhost/%s/' % role.application.client_id
            role.save()

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
                'role': 'security', 'prison': 'IXB',
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
            'role': 'security', 'prison': 'INP',
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

    def test_authentication_requried(self):
        url_list = reverse('accountrequest-list')
        for method in ('get', 'put', 'patch', 'delete'):  # post allowed
            response = getattr(self.client, method)(url_list)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

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
        Role.objects.get(name='security').assign_to_user(admin)
        url_list = reverse('accountrequest-list')

        mommy.make(AccountRequest, 3, role=cashbook_role, prison=prison)
        response = self.client.get(
            url_list,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(admin, client_id=NOMS_OPS_OAUTH_CLIENT_ID)
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

    def test_decline_requests(self):
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

        latest_email = mail.outbox[-1]
        self.assertSequenceEqual(latest_email.to, ['mark@example.com'])
        self.assertIn(role.application.name.lower(), latest_email.subject)
        self.assertIn(role.application.name.lower(), latest_email.body)

        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count)

    def test_confirm_new_requests(self):
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

            latest_email = mail.outbox[-1]
            self.assertSequenceEqual(latest_email.to, [request.email])
            self.assertIn(role.application.name.lower(), latest_email.subject)
            self.assertIn(role.application.name.lower(), latest_email.body)
            self.assertIn(role.login_url, latest_email.body)
            self.assertIn(user.username, latest_email.body)
            password = re.search(r'Password:\s+(\S+)', latest_email.body).group(1)
            self.assertTrue(user.check_password(password))

        assert_user_created({}, user_admin=False)
        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + 1)

        assert_user_created({'user_admin': 'true'}, user_admin=True)
        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + 2)

    def test_confirm_new_requests_with_multiple_prisons(self):
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

        user = User.objects.get(username=request.username)
        self.assertSetEqual(
            set(user.prisonusermapping.prisons.values_list('nomis_id', flat=True)),
            set(Prison.objects.values_list('nomis_id', flat=True)),
            msg='User should get all prisons, not just requested one'
        )

        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + 1)

    def test_confirm_requests_with_existing_user(self):
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
        for scenario in scenarios:
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

            latest_email = mail.outbox[-1]
            self.assertSequenceEqual(latest_email.to, [request.email])
            self.assertIn(role.application.name.lower(), latest_email.subject)
            self.assertIn(role.application.name.lower(), latest_email.body)
            self.assertIn(role.login_url, latest_email.body)
            self.assertIn(refreshed_user.username, latest_email.body)
            self.assertNotIn('Password', latest_email.body)

        self.assertFalse(AccountRequest.objects.exists())
        self.assertEqual(User.objects.count(), user_count + len(scenarios))

    def test_confirm_requests_with_existing_user_with_multiple_prisons(self):
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
