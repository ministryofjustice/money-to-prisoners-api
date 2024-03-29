from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from core.permissions import ActionsBasedPermissions
from mtp_auth.constants import (
    CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, SEND_MONEY_CLIENT_ID,
)
from mtp_auth.models import PrisonUserMapping


class UserPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.change_%(model_name)s'],
    })
    actions_allowed_on_self = {'partial_update', 'destroy'}

    def has_permission(self, request, view):
        if view.action in self.actions_allowed_on_self:
            return True
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if view.action in self.actions_allowed_on_self:
            return obj == request.user or self.user_has_action_permissions(request.user, view)
        return super().has_object_permission(request, view, obj)


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
    client_id = (CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID)


class CashbookClientIDPermissions(ClientIDPermissions):
    client_id = CASHBOOK_OAUTH_CLIENT_ID


class BankAdminClientIDPermissions(ClientIDPermissions):
    client_id = BANK_ADMIN_OAUTH_CLIENT_ID


class NomsOpsClientIDPermissions(ClientIDPermissions):
    client_id = NOMS_OPS_OAUTH_CLIENT_ID


class SendMoneyClientIDPermissions(ClientIDPermissions):
    client_id = SEND_MONEY_CLIENT_ID


class AccountRequestPermissions(BasePermission):
    supported_clients = (CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID)

    def has_permission(self, request, view):
        action = getattr(view, 'action', '')
        if action == 'create':
            return request.user and not request.user.is_authenticated
        if action == 'list' and not request.user.is_authenticated:
            return True
        if action in ('list', 'retrieve', 'partial_update', 'destroy'):
            return IsUserAdmin.is_user_admin(request) and self.supported_app(request)
        return False

    def supported_app(self, request):
        return request.auth.application.client_id in self.supported_clients

    def has_object_permission(self, request, view, obj):
        return obj.role.application == request.auth.application


class IsUserAdmin(BasePermission):
    @classmethod
    def is_user_admin(cls, request):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.groups.filter(name='UserAdmin').exists()
        )

    def has_permission(self, request, view):
        return self.is_user_admin(request)

    def has_object_permission(self, request, view, obj):
        return self.is_user_admin(request)


class UserMappedToPrison(BasePermission):
    @classmethod
    def with_field(cls, field_name):
        return lambda: cls(field_name)

    def __init__(self, field_name):
        self.field_name = field_name

    def has_permission(self, request: Request, view):
        if not super().has_permission(request, view):
            return False

        if view.action in ('create', 'update', 'partial_update') and self.field_name in request.data:
            prison_id = request.data[self.field_name]
            user_prisons = PrisonUserMapping.objects.get_prison_set_for_user(request.user)
            return user_prisons.filter(nomis_id=prison_id).exists()

        # retrieve and destroy are checked by has_object_permission
        # list action is always permitted
        return True

    def has_object_permission(self, request: Request, view, obj):
        if not super().has_object_permission(request, view, obj):
            return False

        # retrieve, update, partial_update, destroy
        prison_id = getattr(obj, self.field_name).nomis_id
        user_prisons = PrisonUserMapping.objects.get_prison_set_for_user(request.user)
        return user_prisons.filter(nomis_id=prison_id).exists()
