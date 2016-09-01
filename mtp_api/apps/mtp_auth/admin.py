from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin
from django.contrib.admin.models import LogEntry, CHANGE as CHANGE_LOG_ENTRY
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.admin.templatetags.admin_list import _boolean_icon
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _
from oauth2_provider.admin import RawIDAdmin
from oauth2_provider.models import Grant, AccessToken, RefreshToken, get_application_model

from mtp_auth.forms import RestrictedUserCreationForm, RestrictedUserChangeForm
from mtp_auth.models import ApplicationGroupMapping, ApplicationUserMapping, FailedLoginAttempt, PrisonUserMapping

User = get_user_model()
Application = get_application_model()
for _model in [User, Application, Grant, AccessToken, RefreshToken]:
    admin.site.unregister(_model)


@admin.register(Application)
class ApplicationAdmin(RawIDAdmin):
    ordering = ('name',)
    list_display = ('name', 'client_id')


@admin.register(Grant)
class GrantAdmin(RawIDAdmin):
    ordering = ('-expires',)
    list_display = ('code', 'application', 'user', 'expires')
    list_filter = ('application',)


class RefreshTokenInline(admin.StackedInline):
    model = RefreshToken
    raw_id_fields = ('user',)


@admin.register(AccessToken)
class AccessTokenAdmin(RawIDAdmin):
    ordering = ('-expires',)
    list_display = ('token', 'application', 'user', 'expires')
    list_filter = ('application',)
    inlines = (RefreshTokenInline,)


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
class UserAdmin(DjangoUserAdmin):
    list_display = DjangoUserAdmin.list_display + ('account_locked',)
    list_filter = DjangoUserAdmin.list_filter + (
        'prisonusermapping__prisons',
        'applicationusermapping__application'
    )
    actions = DjangoUserAdmin.actions + ['remove_account_lockouts']
    add_form = RestrictedUserCreationForm
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
