from django.contrib import admin
from django.contrib.admin import ModelAdmin

from .models import Prison, PrisonerLocation


class PrisonAdmin(ModelAdmin):
    ordering = ('name',)
    list_display = ('name', 'nomis_id', 'general_ledger_code')


class PrisonerLocationAdmin(ModelAdmin):
    ordering = ('prisoner_number',)
    list_display = ('prisoner_name', 'prisoner_number', 'prisoner_dob', 'prison')
    list_filter = ('prison',)
    search_fields = ('prisoner_name', 'prisoner_number')


admin.site.register(Prison, PrisonAdmin)
admin.site.register(PrisonerLocation, PrisonerLocationAdmin)
