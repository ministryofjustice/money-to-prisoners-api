from django.contrib import admin
from django.contrib.admin import ModelAdmin

from .models import ApplicationUserMapping, PrisonUserMapping


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


admin.site.register(ApplicationUserMapping, ApplicationUserMappingAdmin)
admin.site.register(PrisonUserMapping, PrisonUserMappingAdmin)
