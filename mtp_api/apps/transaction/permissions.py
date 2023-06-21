from core.permissions import ActionsBasedPermissions


class TransactionPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.view_%(model_name)s'],
        'patch_processed': ['%(app_label)s.patch_processed_%(model_name)s'],
    })
