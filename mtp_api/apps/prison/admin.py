from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin
from django.utils.translation import gettext

from core.admin import DateFilter
from prison.models import (
    Prison, Population, Category,
    PrisonBankAccount, RemittanceEmail,
    PrisonerLocation, PrisonerCreditNoticeEmail,
)


@admin.register(Population)
class PopulationAdmin(ModelAdmin):
    list_display = ('name', 'description')


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'description')


@admin.register(Prison)
class PrisonAdmin(ModelAdmin):
    list_display = ('name', 'nomis_id', 'general_ledger_code', 'private_estate')
    list_filter = ('region', 'populations', 'categories', 'private_estate')
    search_fields = ('nomis_id', 'general_ledger_code', 'name', 'region')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.name.upper() == obj.short_name.upper():
            self.message_user(request=request, level=messages.WARNING,
                              message=gettext('Prison name does not start with a standard prefix.') +
                              ' (%s)' % ', '.join(Prison.name_prefixes))


@admin.register(PrisonBankAccount)
class PrisonBankAccountAdmin(ModelAdmin):
    list_display = ('prison',)


@admin.register(RemittanceEmail)
class RemittanceEmailAdmin(ModelAdmin):
    list_display = ('prison', 'email')


@admin.register(PrisonerLocation)
class PrisonerLocationAdmin(ModelAdmin):
    list_display = ('prisoner_name', 'prisoner_number', 'prisoner_dob', 'prison')
    list_filter = ('prison', ('prisoner_dob', DateFilter))
    search_fields = ('prisoner_name', 'prisoner_number', 'single_offender_id')
    readonly_fields = ('created_by',)


@admin.register(PrisonerCreditNoticeEmail)
class PrisonerCreditNoticeEmailAdmin(ModelAdmin):
    list_display = ('prison', 'email')
