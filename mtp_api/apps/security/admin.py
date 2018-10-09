from django.contrib import admin
from django.utils.translation import gettext, gettext_lazy as _

from core.admin import add_short_description
from security.models import (
    SenderProfile, PrisonerProfile, BankTransferSenderDetails,
    DebitCardSenderDetails, SavedSearch, SearchFilter,
)
from transaction.utils import format_amount


class BankTransferSenderDetailsAdminInline(admin.StackedInline):
    model = BankTransferSenderDetails
    extra = 0


class DebitCardSenderDetailsAdminInline(admin.StackedInline):
    model = DebitCardSenderDetails
    extra = 0
    readonly_fields = ('cardholder_names',)

    @add_short_description(_('cardholder names'))
    def cardholder_names(self, instance):
        return ', '.join(instance.cardholder_names.values_list('name', flat=True))


@admin.register(SenderProfile)
class SenderProfileAdmin(admin.ModelAdmin):
    ordering = ('-credit_count',)
    list_display = ('sender_names', 'sender_type', 'credit_count', 'formatted_credit_total')
    inlines = (BankTransferSenderDetailsAdminInline, DebitCardSenderDetailsAdminInline)
    search_fields = (
        'bank_transfer_details__sender_bank_account__sender_name',
        'bank_transfer_details__sender_bank_account__sender_sort_code',
        'bank_transfer_details__sender_bank_account__sender_account_number',
        'bank_transfer_details__sender_bank_account__sender_roll_number',
        'debit_card_details__card_number_last_digits',
        'debit_card_details__card_expiry_date',
        'debit_card_details__cardholder_name__name',
    )

    @add_short_description(_('sender names'))
    def sender_names(self, instance):
        return ', '.join(instance.get_sorted_sender_names())

    @add_short_description(_('payment method'))
    def sender_type(self, instance):
        sender_types = []
        if instance.bank_transfer_details.exists():
            sender_types.append(gettext('Bank transfer'))
        if instance.debit_card_details.exists():
            sender_types.append(gettext('Debit card'))
        return ', '.join(sender_types)

    @add_short_description(_('credit total'))
    def formatted_credit_total(self, instance):
        return format_amount(instance.credit_total)


@admin.register(PrisonerProfile)
class PrisonerProfileAdmin(admin.ModelAdmin):
    ordering = ('-credit_count',)
    list_display = ('prisoner_number', 'credit_count', 'formatted_credit_total')
    search_fields = ('prisoner_name', 'prisoner_number', 'prisons__name', 'recipient_name__name')
    readonly_fields = ('prisons', 'provided_names')
    exclude = ('senders',)

    @add_short_description(_('credit total'))
    def formatted_credit_total(self, instance):
        return format_amount(instance.credit_total)

    @add_short_description(_('names specified by senders'))
    def provided_names(self, instance):
        return ', '.join(instance.provided_names.values_list('name', flat=True))


class SearchFilterAdminInline(admin.StackedInline):
    model = SearchFilter
    extra = 0
    readonly_fields = ('saved_search',)


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    inlines = (SearchFilterAdminInline,)
    list_display = ('user', 'description', 'formatted_filters', 'site_url',)

    @add_short_description(_('filters'))
    def formatted_filters(self, instance):
        filters = instance.filters.all()

        if len(filters) == 0:
            return ''
        return ', '.join([str(searchfilter) for searchfilter in filters])
