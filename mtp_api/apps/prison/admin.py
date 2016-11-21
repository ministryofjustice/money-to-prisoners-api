from django.contrib import admin
from django.contrib.admin import ModelAdmin

from core.admin import DateFilter
from prison.models import Prison, PrisonerLocation, Population, Category


@admin.register(Population)
class PopulationAdmin(ModelAdmin):
    list_display = ('name', 'description')


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'description')


@admin.register(Prison)
class PrisonAdmin(ModelAdmin):
    list_display = ('name', 'nomis_id', 'general_ledger_code')
    list_filter = ('region', 'populations', 'categories')
    search_fields = ('nomis_id', 'general_ledger_code', 'name', 'region')


@admin.register(PrisonerLocation)
class PrisonerLocationAdmin(ModelAdmin):
    ordering = ('prisoner_number',)
    list_display = ('prisoner_name', 'prisoner_number', 'prisoner_dob', 'prison')
    list_filter = ('prison', ('prisoner_dob', DateFilter))
    search_fields = ('prisoner_name', 'prisoner_number')
