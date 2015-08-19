from rest_framework.permissions import BasePermission

from .constants import CASHBOOK_OAUTH_CLIENT_ID, \
    BANK_ADMIN_OAUTH_CLIENT_ID, PRISONER_LOCATION_OAUTH_CLIENT_ID


class ClientIDPermissions(BasePermission):
    """
    Permissions class which checks that an API view can only be accessed
    by a specific oauth application.
    """
    client_id = None

    def has_permission(self, request, view):
        if not request.auth or not request.auth.application:
            return False
        return self.client_id == request.auth.application.client_id


class CashbookClientIDPermissions(ClientIDPermissions):
    client_id = CASHBOOK_OAUTH_CLIENT_ID


class BankAdminClientIDPermissions(ClientIDPermissions):
    client_id = BANK_ADMIN_OAUTH_CLIENT_ID


class PrisonerLocationClientIDPermissions(ClientIDPermissions):
    client_id = PRISONER_LOCATION_OAUTH_CLIENT_ID
