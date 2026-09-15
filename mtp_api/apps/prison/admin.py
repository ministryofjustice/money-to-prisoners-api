from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin, RelatedFieldListFilter
from django.contrib.admin.models import LogEntry, CHANGE as CHANGE_LOG_ENTRY
from django.contrib.admin.options import get_content_type_for_model
from django.db import models
from django.utils.translation import gettext, gettext_lazy as _
from mtp_common.utils import format_currency

from core.admin import DateFilter, add_short_description
from prison.models import (
    Prison, Population, Category,
    PrisonBankAccount, RemittanceEmail,
    PrisonerLocation, PrisonerCreditNoticeEmail,
    PrisonerBalance, PrisonerValidityAttempt,
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
    search_fields = ('prisoner_name', 'prisoner_number')
    readonly_fields = ('created_by',)


@admin.register(PrisonerCreditNoticeEmail)
class PrisonerCreditNoticeEmailAdmin(ModelAdmin):
    list_display = ('prison', 'email')


class LastModifiedPrisonFilter(RelatedFieldListFilter):
    def field_choices(self, field, request, model_admin):
        choices = model_admin.get_queryset(request).order_by() \
            .values('prison__pk', 'prison__name') \
            .annotate(modified=models.Max('modified'))
        choices = [
            (prison['prison__pk'], f'{prison["prison__name"]} ({prison["modified"].strftime("%d %b")})')
            for prison in choices
        ]
        return sorted(choices, key=lambda choice: choice[1])


@admin.register(PrisonerBalance)
class PrisonerBalanceAdmin(ModelAdmin):
    list_display = ('prisoner_number', 'prison', 'formatted_amount')
    list_filter = (('prison', LastModifiedPrisonFilter),)
    ordering = ('prisoner_number',)
    search_fields = ('prisoner_number',)
    readonly_fields = ('created',)

    @add_short_description(_('amount'))
    def formatted_amount(self, instance):
        return format_currency(instance.amount)


@admin.register(PrisonerValidityAttempt)
class PrisonerValidityAttemptAdmin(ModelAdmin):
    list_display = ('created', 'ip_address', 'matched', 'prisoner_number_hash')
    list_filter = ('matched', ('created', DateFilter))
    search_fields = ('ip_address', 'prisoner_number_hash')
    readonly_fields = ('created', 'ip_address', 'matched', 'prisoner_number_hash')
    actions = ['clear_attempts_for_ip_addresses']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @add_short_description(_('Clear all attempts from selected IP addresses'))
    def clear_attempts_for_ip_addresses(self, request, queryset):
        # support route for lifting a rate limit applied in error, mirroring the account lockout removal
        ip_addresses = sorted(filter(None, set(queryset.values_list('ip_address', flat=True))))
        if not ip_addresses:
            messages.info(request, _('No IP addresses selected'))
            return
        deleted, _details = PrisonerValidityAttempt.objects.filter(ip_address__in=ip_addresses).delete()
        LogEntry.objects.create(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(PrisonerValidityAttempt).pk,
            object_id='',
            object_repr=gettext('Clear prisoner validity attempts'),
            action_flag=CHANGE_LOG_ENTRY,
            change_message=', '.join(ip_addresses),
        )
        messages.info(request, gettext('Cleared %(count)d attempts from %(ip_addresses)s') % {
            'count': deleted,
            'ip_addresses': ', '.join(ip_addresses),
        })
