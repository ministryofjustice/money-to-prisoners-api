import mock
from django.test import TestCase

from mtp_auth.permissions import ClientIDPermissions


class TestClientIDPermissions(ClientIDPermissions):
    client_id = 'test'


class ClientIDPermissionsTestCase(TestCase):

    def setUp(self):
        super(ClientIDPermissionsTestCase, self).setUp()
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
