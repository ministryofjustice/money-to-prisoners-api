from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin
from django.contrib.admin.models import LogEntry, CHANGE as CHANGE_LOG_ENTRY
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.admin.templatetags.admin_list import _boolean_icon
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from mtp_auth.forms import RestrictedUserChangeForm
from mtp_auth.models import ApplicationGroupMapping, ApplicationUserMapping, FailedLoginAttempt, PrisonUserMapping

User = get_user_model()
if admin.site.is_registered(User):
    admin.site.unregister(User)


@admin.register(ApplicationGroupMapping)
class ApplicationGroupMappingAdmin(ModelAdmin):
    ordering = ('group__name', 'application')
    list_display = ('group', 'application')
    list_filter = ('application',)


@admin.register(ApplicationUserMapping)
class ApplicationUserMappingAdmin(ModelAdmin):
    ordering = ('user__username', 'application')
    list_display = ('user', 'application')
    list_filter = ('application',)


@admin.register(PrisonUserMapping)
class PrisonUserMappingAdmin(ModelAdmin):
    ordering = ('user__username',)
    list_display = ('user', 'prison_names')

    @classmethod
    def prison_names(cls, mapping):
        prisons = mapping.prisons.all()
        suffix = ''
        if prisons.count() > 4:
            prisons = prisons[:4]
            suffix = '…'
        return ', '.join(map(lambda prison: prison.name, prisons)) \
               + suffix


@admin.register(User)
class MtpUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ('account_locked',)
    actions = UserAdmin.actions + ['remove_account_lockouts']
    form = RestrictedUserChangeForm

    def remove_account_lockouts(self, request, instances):
        accounts = []
        for instance in instances:
            attempts = FailedLoginAttempt.objects.filter(user=instance)
            if attempts.count():
                attempts.delete()
                LogEntry.objects.log_action(
                    user_id=request.user.pk,
                    content_type_id=get_content_type_for_model(instance).pk, object_id=instance.pk,
                    object_repr=_('Remove lockouts'),
                    action_flag=CHANGE_LOG_ENTRY,
                )
                accounts.append(instance)
        if accounts:
            messages.info(request, 'Removed account lockout for %s' %
                          ', '.join(map(str, accounts)))
        else:
            messages.info(request, 'No account lockouts to remove')

    def account_locked(self, instance):
        return _boolean_icon(instance.is_locked_out)

    account_locked.short_description = _('account locked')
