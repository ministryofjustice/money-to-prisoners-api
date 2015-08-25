from rest_framework.permissions import BasePermission

from mtp_auth.models import PrisonUserMapping

from core.permissions import ActionsBasedPermissions


class IsOwner(BasePermission):

    def has_permission(self, request, view):
        return str(request.user.id) == view.kwargs.get('user_id')


class IsOwnPrison(BasePermission):

    def has_permission(self, request, view):
        try:
            prison_user_mapping = request.user.prisonusermapping
        except PrisonUserMapping.DoesNotExist:
            return False

        return prison_user_mapping.prisons.filter(pk=view.kwargs.get('prison_id')).exists()


class TransactionPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.view_%(model_name)s'],
        'retrieve': ['%(app_label)s.view_%(model_name)s'],
        'lock': ['%(app_label)s.lock_%(model_name)s'],
        'unlock': ['%(app_label)s.unlock_%(model_name)s'],
        'patch_credited': ['%(app_label)s.patch_credited_%(model_name)s']
    })
