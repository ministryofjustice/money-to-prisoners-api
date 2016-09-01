from rest_framework.permissions import BasePermission

from core.permissions import ActionsBasedPermissions
from .constants import (
    CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, SEND_MONEY_CLIENT_ID
)


class UserPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.change_%(model_name)s'],
    })


class ClientIDPermissions(BasePermission):
    """
    Permissions class which checks that an API view can only be accessed
    by a specific oauth application.
    """
    client_id = None

    def has_permission(self, request, view):
        if not request.auth or not request.auth.application:
            return False
        if isinstance(self.client_id, (list, tuple, set)):
            return request.auth.application.client_id in self.client_id
        return self.client_id == request.auth.application.client_id


def get_client_permissions_class(*client_ids):
    return type(
        'CustomClientIDPermissions',
        (ClientIDPermissions,),
        {'client_id': tuple(client_ids)}
    )


class AnyAdminClientIDPermissions(ClientIDPermissions):
    client_id = (CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID,
                 NOMS_OPS_OAUTH_CLIENT_ID)


class CashbookClientIDPermissions(ClientIDPermissions):
    client_id = CASHBOOK_OAUTH_CLIENT_ID


class BankAdminClientIDPermissions(ClientIDPermissions):
    client_id = BANK_ADMIN_OAUTH_CLIENT_ID


class NomsOpsClientIDPermissions(ClientIDPermissions):
    client_id = NOMS_OPS_OAUTH_CLIENT_ID


class SendMoneyClientIDPermissions(ClientIDPermissions):
    client_id = SEND_MONEY_CLIENT_ID
