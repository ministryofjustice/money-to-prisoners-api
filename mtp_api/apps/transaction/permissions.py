from rest_framework.permissions import BasePermission

from core.permissions import ActionsBasedPermissions


class IsOwner(BasePermission):

    def has_permission(self, request, view):
        return str(request.user.id) == view.kwargs.get('user_id')


class IsOwnPrison(BasePermission):

    def has_permission(self, request, view):
        return request.user.prisonusermapping.prisons.filter(pk=view.kwargs.get('prison_id')).exists()


class TransactionPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.view_%(model_name)s'],
        'retrieve': ['%(app_label)s.view_%(model_name)s'],
        'take': ['%(app_label)s.take_%(model_name)s'],
        'release': ['%(app_label)s.release_%(model_name)s'],
        'patch_credited': ['%(app_label)s.patch_credited_%(model_name)s']
    })
