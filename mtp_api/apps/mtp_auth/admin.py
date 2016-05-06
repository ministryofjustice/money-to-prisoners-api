from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin
from django.contrib.admin.templatetags.admin_list import _boolean_icon
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

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
    actions = ['remove_account_lockouts']
    form = RestrictedUserChangeForm

    def remove_account_lockouts(self, request, instances):
        for instance in instances:
            FailedLoginAttempt.objects.filter(user=instance).delete()
        messages.info(request, 'Removed account lockout for %s' %
                      ', '.join(map(str, instances)))

    @classmethod
    def account_locked(cls, instance):
        return _boolean_icon(FailedLoginAttempt.objects.is_locked_out(user=instance))
