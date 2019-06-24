from django.contrib import admin
from django.utils.translation import gettext, gettext_lazy as _

from core.admin import add_short_description
from security.models import (
    SenderProfile, PrisonerProfile, BankTransferSenderDetails,
    DebitCardSenderDetails, SavedSearch, SearchFilter, RecipientProfile,
    SenderTotals, RecipientTotals, PrisonerTotals
)


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


class SenderTotalsAdminInline(admin.StackedInline):
    model = SenderTotals
    extra = 0


@admin.register(SenderProfile)
class SenderProfileAdmin(admin.ModelAdmin):
    ordering = ('-pk',)
    list_display = ('sender_names', 'sender_type',)
    inlines = (
        BankTransferSenderDetailsAdminInline,
        DebitCardSenderDetailsAdminInline,
        SenderTotalsAdminInline,
    )
    search_fields = (
        'bank_transfer_details__sender_bank_account__sender_name',
        'bank_transfer_details__sender_bank_account__sort_code',
        'bank_transfer_details__sender_bank_account__account_number',
        'bank_transfer_details__sender_bank_account__roll_number',
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


class RecipientTotalsAdminInline(admin.StackedInline):
    model = RecipientTotals
    extra = 0


@admin.register(RecipientProfile)
class RecipientProfileAdmin(admin.ModelAdmin):
    ordering = ('-pk',)
    list_display = (
        'sort_code',
        'account_number',
    )
    search_fields = (
        'bank_transfer_details__recipient_bank_account__sort_code',
        'bank_transfer_details__recipient_bank_account__account_number',
        'bank_transfer_details__recipient_bank_account__roll_number',
        'disbursements__recipient_first_name',
        'disbursements__recipient_last_name',
    )
    inlines = (RecipientTotalsAdminInline,)

    @add_short_description(_('sort code'))
    def sort_code(self, instance):
        return (
            instance.bank_transfer_details.first().recipient_bank_account.sort_code
            if instance.bank_transfer_details.first()
            else 'Cheque'
        )

    @add_short_description(_('account number'))
    def account_number(self, instance):
        return (
            instance.bank_transfer_details.first().recipient_bank_account.account_number
            if instance.bank_transfer_details.first()
            else 'Cheque'
        )


class PrisonerTotalsAdminInline(admin.StackedInline):
    model = PrisonerTotals
    extra = 0


@admin.register(PrisonerProfile)
class PrisonerProfileAdmin(admin.ModelAdmin):
    ordering = ('-pk',)
    list_display = ('prisoner_number',)
    search_fields = ('prisoner_name', 'prisoner_number', 'prisons__name', 'provided_name__name')
    readonly_fields = ('prisons', 'provided_names',)
    exclude = ('senders', 'recipients',)
    inlines = (PrisonerTotalsAdminInline,)

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
