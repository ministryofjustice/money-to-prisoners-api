from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import ApplicationUserMapping, PrisonUserMapping, FailedLoginAttempt


class ApplicationUserMappingAdmin(ModelAdmin):
    ordering = ('user__username', 'application')
    list_display = ('user', 'application')
    list_filter = ('application',)


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


class MtpUserAdmin(UserAdmin):
    actions = ['remove_account_lockouts']

    def remove_account_lockouts(self, request, instances):
        for instance in instances:
            FailedLoginAttempt.objects.filter(user=instance).delete()
        messages.info(request, 'Removed account lockout for %s' %
                      ', '.join(map(str, instances)))


admin.site.register(ApplicationUserMapping, ApplicationUserMappingAdmin)
admin.site.register(PrisonUserMapping, PrisonUserMappingAdmin)
admin.site.unregister(get_user_model())
admin.site.register(get_user_model(), MtpUserAdmin)
