from core.permissions import ActionsBasedPermissions


class SecurityProfilePermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.view_%(model_name)s'],
    })


class SecurityCheckPermissions(SecurityProfilePermissions):
    actions_perms_map = SecurityProfilePermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'accept': ['%(app_label)s.change_%(model_name)s'],
        'reject': ['%(app_label)s.change_%(model_name)s'],
    })
