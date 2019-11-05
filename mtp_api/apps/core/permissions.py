from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import BasePermission


class ActionsBasedPermissions(BasePermission):
    """
    The request is authenticated using `django.contrib.auth` permissions.
    See: https://docs.djangoproject.com/en/dev/topics/auth/#permissions

    It ensures that the user is authenticated, and has the appropriate
    `add`/`change`/`delete` permissions on the model.

    This permission can only be applied against view classes that
    provide a `.queryset` attribute.

    Permission mapping is defined against view actions ('list', 'retrieve',
    'update', 'destroy' etc.).
    When using custom actions on a view, you would have to add a new
    (key, value) to the mapping and set the permissions you want the class
    to test against.

    This version is slightly better than the
    `rest_framework.permissions.DjangoModelPermissions` one in our use case
    as it's based on actions instead of methods.
    A `POST` that creates a resource and one that makes an action on a resource
    usually have different permissions so they should be treated differently.

    NOTE: This is only meant to work with ViewSets.
    """

    # Map methods into required permission codes.
    # Override this if you need to also provide 'view' permissions,
    # or if you want to provide custom permission codes.
    actions_perms_map = {
        'create': ['%(app_label)s.add_%(model_name)s'],
        'list': [],
        'retrieve': [],
        'update': ['%(app_label)s.change_%(model_name)s'],
        'partial_update': ['%(app_label)s.change_%(model_name)s'],
        'destroy': ['%(app_label)s.delete_%(model_name)s']
    }

    def get_required_permissions(self, action, model_cls):
        """
        Given a model and an HTTP method, return the list of permission
        codes that the user is required to have.
        """
        kwargs = {
            'app_label': model_cls._meta.app_label,
            'model_name': model_cls._meta.model_name,
        }

        # This line raises KeyError if you add a custom action to
        # the view and you forget to add it to the actions_perms_map as
        # well. This is on purpose :-)
        return [perm % kwargs for perm in self.actions_perms_map[action]]

    def user_has_action_permissions(self, user, view):
        if not hasattr(view, 'action'):
            msg = "%s has to have an 'action' property or you have to use a ViewSet"
            raise ImproperlyConfigured(msg % self.__class__.__name__)

        # Workaround to ensure DjangoModelPermissions are not applied
        # to the root view when using DefaultRouter.
        if getattr(view, '_ignore_model_permissions', False):
            return True

        try:
            queryset = view.get_queryset()
        except AttributeError:
            queryset = getattr(view, 'queryset', None)
        if queryset is None:
            msg = (
                'Cannot apply %s on a view that '
                'does not have `.queryset` property or overrides the '
                '`.get_queryset()` method.'
            )
            raise ImproperlyConfigured(msg % self.__class__.__name__)

        # http method does not map to an action, should really cause 405 not 403
        if not view.action:
            return False

        perms = self.get_required_permissions(view.action, queryset.model)
        return user.has_perms(perms)

    def has_permission(self, request, view):
        return self.user_has_action_permissions(request.user, view)


class ActionsBasedViewPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.view_%(model_name)s'],
        'retrieve': ['%(app_label)s.view_%(model_name)s'],
    })


# TODO: Remove once all apps move to NOMIS Elite2
class TokenPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'retrieve': ['%(app_label)s.view_%(model_name)s'],
    })
