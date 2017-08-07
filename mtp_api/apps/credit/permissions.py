from core.permissions import ActionsBasedPermissions


class CreditPermissions(ActionsBasedPermissions):
    actions_perms_map = ActionsBasedPermissions.actions_perms_map.copy()
    actions_perms_map.update({
        'list': ['%(app_label)s.view_%(model_name)s'],
        'retrieve': ['%(app_label)s.view_%(model_name)s'],
        'review': ['%(app_label)s.review_%(model_name)s'],
        'credit': ['%(app_label)s.credit_%(model_name)s'],
    })
