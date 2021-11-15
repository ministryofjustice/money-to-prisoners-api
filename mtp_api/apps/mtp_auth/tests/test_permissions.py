import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.management import call_command
from django.test import TestCase

from core.tests.utils import make_test_users
from mtp_auth.permissions import ClientIDPermissions, IsUserAdmin

User = get_user_model()


class TestClientIDPermissions(ClientIDPermissions):
    client_id = 'test'


class ClientIDPermissionsTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.permissions = TestClientIDPermissions()
        self.request = mock.MagicMock()
        self.view = mock.MagicMock()

    def test_no_permissions_without_auth(self):
        self.request.auth = None
        self.assertFalse(
            self.permissions.has_permission(self.request, self.view)
        )

    def test_no_permissions_without_oauth_application(self):
        self.request.auth.application = None
        self.assertFalse(
            self.permissions.has_permission(self.request, self.view)
        )

    def test_no_permissions_with_mismatching_clients(self):
        self.request.auth.application.client_id = 'different-client-id'

        self.assertFalse(
            self.permissions.has_permission(self.request, self.view)
        )

    def test_has_permissions(self):
        self.request.auth.application.client_id = TestClientIDPermissions.client_id

        self.assertTrue(
            self.permissions.has_permission(self.request, self.view)
        )


class IsUserAdminTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.test_user = make_test_users(clerks_per_prison=1, num_security_fiu_users=0)['prison_clerks'][0]
        self.permissions = IsUserAdmin()
        self.request = mock.MagicMock()
        self.view = mock.MagicMock()

    def test_no_permissions_without_auth(self):
        self.request.user = AnonymousUser()
        self.assertFalse(
            self.permissions.has_permission(self.request, self.view)
        )

    def test_no_permissions_with_auth_but_missing_group(self):
        self.request.user = self.test_user
        self.assertFalse(
            self.permissions.has_permission(self.request, self.view)
        )

    def test_has_permissions_with_auth_and_correct_group(self):
        admin_group = Group.objects.get(name='UserAdmin')
        self.test_user.groups.add(admin_group)
        self.request.user = self.test_user
        self.assertTrue(
            self.permissions.has_permission(self.request, self.view)
        )


class SynchroniseGroupsTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.devnull = open(os.devnull, 'wt')

    def tearDown(self):
        self.devnull.close()
        super().tearDown()

    @mock.patch('mtp_auth.management.commands.sync_group_permissions.input')
    def test_makes_all_groups(self, mock_input):
        mock_input.return_value = 'y'
        self.assertFalse(Group.objects.exists())
        call_command('sync_group_permissions', stdout=self.devnull, stderr=self.devnull)
        self.assertEqual(Group.objects.count(), 9)

    @mock.patch('mtp_auth.management.commands.sync_group_permissions.input')
    def test_no_effect_if_cancelled(self, mock_input):
        mock_input.return_value = 'n'
        self.assertFalse(Group.objects.exists())
        call_command('sync_group_permissions', stdout=self.devnull, stderr=self.devnull)
        self.assertFalse(Group.objects.exists())

    @mock.patch('mtp_auth.management.commands.sync_group_permissions.input')
    def test_makes_missing_groups(self, mock_input):
        mock_input.return_value = 'y'
        Group.objects.create(name='PrisonClerk')
        Group.objects.create(name='Security')
        call_command('sync_group_permissions', stdout=self.devnull, stderr=self.devnull)
        self.assertEqual(Group.objects.count(), 9)

    @mock.patch('mtp_auth.management.commands.sync_group_permissions.input')
    def test_adds_missing_permissions(self, mock_input):
        mock_input.return_value = ''  # specifies default answer, won't remove extra permissions
        expected_permission = Permission.objects.get_by_natural_key('view_credit', 'credit', 'credit')
        unexpected_permission = Permission.objects.get_by_natural_key('delete_user', 'auth', 'user')
        group = Group.objects.create(name='PrisonClerk')
        group.permissions.set([expected_permission, unexpected_permission])
        call_command('sync_group_permissions', stdout=self.devnull, stderr=self.devnull)
        group = Group.objects.get(name='PrisonClerk')
        self.assertTrue(group.permissions.filter(pk=expected_permission.pk).exists())
        self.assertTrue(group.permissions.filter(pk=unexpected_permission.pk).exists())
        self.assertEqual(group.permissions.count(), 10)

    @mock.patch('mtp_auth.management.commands.sync_group_permissions.input')
    def test_sets_permissions_exactly(self, mock_input):
        mock_input.return_value = 'y'  # specifies default answer, will remove extra permissions
        expected_permission = Permission.objects.get_by_natural_key('view_credit', 'credit', 'credit')
        unexpected_permission = Permission.objects.get_by_natural_key('delete_user', 'auth', 'user')
        group = Group.objects.create(name='PrisonClerk')
        group.permissions.set([expected_permission, unexpected_permission])
        call_command('sync_group_permissions', stdout=self.devnull, stderr=self.devnull)
        group = Group.objects.get(name='PrisonClerk')
        self.assertTrue(group.permissions.filter(pk=expected_permission.pk).exists())
        self.assertFalse(group.permissions.filter(pk=unexpected_permission.pk).exists())
        self.assertEqual(group.permissions.count(), 9)
