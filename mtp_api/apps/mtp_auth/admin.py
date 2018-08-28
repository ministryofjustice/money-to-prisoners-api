from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin
from django.contrib.admin.models import LogEntry, CHANGE as CHANGE_LOG_ENTRY
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.admin.templatetags.admin_list import _boolean_icon
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _
from oauth2_provider.admin import (
    ApplicationAdmin, GrantAdmin, AccessTokenAdmin, RefreshTokenAdmin
)
from oauth2_provider.models import Grant, AccessToken, RefreshToken, get_application_model

from core.admin import add_short_description
from mtp_auth.forms import RestrictedUserCreationForm, RestrictedUserChangeForm
from mtp_auth.models import Role, ApplicationUserMapping, FailedLoginAttempt, PrisonUserMapping, AccountRequest, Flag

User = get_user_model()
Application = get_application_model()
for _model in [User, Application, Grant, AccessToken, RefreshToken]:
    admin.site.unregister(_model)

admin.site.register(Application, ApplicationAdmin)
admin.site.register(Grant, GrantAdmin)
admin.site.register(AccessToken, AccessTokenAdmin)
admin.site.register(RefreshToken, RefreshTokenAdmin)


@admin.register(Role)
class RoleAdmin(ModelAdmin):
    list_display = ('name', 'key_group', 'all_groups', 'application')
    list_filter = ('key_group', 'application')

    def all_groups(self, instance):
        return ', '.join(sorted(group.name for group in instance.groups))


@admin.register(ApplicationUserMapping)
class ApplicationUserMappingAdmin(ModelAdmin):
    ordering = ('user__username', 'application')
    list_display = ('user', 'application')
    list_filter = ('application',)
    search_fields = ('user__username',)


@admin.register(PrisonUserMapping)
class PrisonUserMappingAdmin(ModelAdmin):
    ordering = ('user__username',)
    list_display = ('user', 'prison_names')
    search_fields = ('user__username',)

    @classmethod
    def prison_names(cls, mapping):
        prisons = mapping.prisons.all()
        suffix = ''
        if prisons.count() > 4:
            prisons = prisons[:4]
            suffix = '…'
        return ', '.join(map(lambda prison: prison.name, prisons)) \
               + suffix


class FlagInline(admin.TabularInline):
    model = Flag
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = DjangoUserAdmin.list_display + ('account_locked',)
    list_filter = DjangoUserAdmin.list_filter + (
        'prisonusermapping__prisons',
        'applicationusermapping__application'
    )
    actions = DjangoUserAdmin.actions + ['remove_account_lockouts']
    add_form = RestrictedUserCreationForm
    form = RestrictedUserChangeForm
    inlines = DjangoUserAdmin.inlines + [FlagInline]

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

    @add_short_description(_('account locked'))
    def account_locked(self, instance):
        return _boolean_icon(instance.is_locked_out)

    def response_change(self, request, obj):
        response = super().response_change(request, obj)
        if obj.groups.filter(name='UserAdmin').exists() and Role.objects.get_roles_for_user(obj).count() != 1:
            messages.error(request, _('This user will be unable to manage user accounts. '
                                      'Either remove ‘UserAdmin’ group or choose fewer other groups.'))
        if obj.groups.filter(name='PrisonClerk').exists() and (not hasattr(obj, 'prisonusermapping')
                                                               or obj.prisonusermapping.prisons.count() == 0):
            messages.error(request, _('Prison clerks must be assigned to a prison.'))
        return response


@admin.register(AccountRequest)
class AccountRequestAdmin(ModelAdmin):
    list_display = ('username', 'email', 'role', 'prison', 'user_exists')
    list_filter = ('role', 'prison')

    @add_short_description(_('existing user'))
    def user_exists(self, instance):
        return _boolean_icon(User.objects.filter(username=instance.username).exists())
