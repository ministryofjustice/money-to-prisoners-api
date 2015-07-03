from rest_framework.permissions import BasePermission

class IsOwner(BasePermission):

    def has_permission(self, request, view):
        return str(request.user.id) == view.kwargs.get('user_id')

class IsOwnPrison(BasePermission):

    def has_permission(self, request, view):
        return request.user.prisonusermapping.prisons.filter(pk=view.kwargs.get('prison_id')).exists()
