from core.permissions import ActionsBasedPermissions


class CreditPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.view_%(model_name)s'],
        'retrieve': ['%(app_label)s.view_%(model_name)s'],
        'lock': ['%(app_label)s.lock_%(model_name)s'],
        'unlock': ['%(app_label)s.unlock_%(model_name)s'],
        'patch_credited': ['%(app_label)s.patch_credited_%(model_name)s']
    })
