from rest_framework.permissions import BasePermission

from core.permissions import ActionsBasedPermissions


class IsOwner(BasePermission):

    def has_permission(self, request, view):
        return str(request.user.id) == view.kwargs.get('user_id')


class IsOwnPrison(BasePermission):

    def has_permission(self, request, view):
        return request.user.prisonusermapping.prisons.filter(pk=view.kwargs.get('prison_id')).exists()


class TransactionPermissions(ActionsBasedPermissions):
    actions_perms_map = {
        'create': ['%(app_label)s.add_%(model_name)s'],
        'list': ['%(app_label)s.view_%(model_name)s'],
        'retrieve': ['%(app_label)s.view_%(model_name)s'],
        'update': ['%(app_label)s.change_%(model_name)s'],
        'partial_update': ['%(app_label)s.change_%(model_name)s'],
        'destroy': ['%(app_label)s.delete_%(model_name)s'],
        'take': ['%(app_label)s.take_%(model_name)s'],
        'release': ['%(app_label)s.release_%(model_name)s'],
        'patch_credited': ['%(app_label)s.patch_credited_%(model_name)s']
    }
