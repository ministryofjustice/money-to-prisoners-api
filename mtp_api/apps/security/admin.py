from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import add_short_description
from security.models import (
    SenderProfile, PrisonerProfile, BankTransferSenderDetails,
    DebitCardSenderDetails, SecurityDataUpdate
)
from transaction.utils import format_amount


class BankTransferSenderDetailsAdminInline(admin.StackedInline):
    model = BankTransferSenderDetails
    extra = 0


class DebitCardSenderDetailsAdminInline(admin.StackedInline):
    model = DebitCardSenderDetails
    extra = 0
    readonly_fields = ('cardholder_names',)

    def cardholder_names(self, instance):
        return ', '.join(instance.cardholder_names.values_list('name', flat=True))


@admin.register(SenderProfile)
class SenderProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'credit_count', 'formatted_credit_total', 'sender_type')
    inlines = (BankTransferSenderDetailsAdminInline, DebitCardSenderDetailsAdminInline)
    search_fields = (
        'bank_transfer_details__sender_name',
        'bank_transfer_details__sender_sort_code',
        'bank_transfer_details__sender_account_number',
        'bank_transfer_details__sender_roll_number',
        'debit_card_details__card_number_last_digits',
        'debit_card_details__card_expiry_date',
        'debit_card_details__cardholder_name__name',
    )
    readonly_fields = ('recipients',)

    def sender_type(self, instance):
        sender_types = []
        if instance.bank_transfer_details.exists():
            sender_types.append('Bank transfer')
        if instance.debit_card_details.exists():
            sender_types.append('Debit card')
        return ', '.join(sender_types)

    def recipients(self, instance):
        return ', '.join(map(str, instance.prisoners.all()))

    @add_short_description(_('credit_total'))
    def formatted_credit_total(self, instance):
        return format_amount(instance.credit_total)


@admin.register(PrisonerProfile)
class PrisonerProfileAdmin(admin.ModelAdmin):
    list_display = ('prisoner_number', 'credit_count', 'formatted_credit_total')
    search_fields = ('prisoner_name', 'prisoner_number', 'prisons__name')
    readonly_fields = ('prisons', 'senders',)

    @add_short_description(_('credit_total'))
    def formatted_credit_total(self, instance):
        return format_amount(instance.credit_total)


@admin.register(SecurityDataUpdate)
class SecurityDataUpdateAdmin(admin.ModelAdmin):
    pass
