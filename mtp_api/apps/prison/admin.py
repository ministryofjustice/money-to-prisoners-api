from django.contrib import admin
from django.contrib.admin import ModelAdmin

from core.admin import DateFilter
from prison.models import Prison, PrisonerLocation, Population, Category


@admin.register(Prison)
class PrisonAdmin(ModelAdmin):
    ordering = ('name',)
    list_display = ('name', 'nomis_id', 'general_ledger_code')
    list_filter = ('region',)


@admin.register(PrisonerLocation)
class PrisonerLocationAdmin(ModelAdmin):
    ordering = ('prisoner_number',)
    list_display = ('prisoner_name', 'prisoner_number', 'prisoner_dob', 'prison')
    list_filter = ('prison', ('prisoner_dob', DateFilter))
    search_fields = ('prisoner_name', 'prisoner_number')


admin.site.register(Population)
admin.site.register(Category)
