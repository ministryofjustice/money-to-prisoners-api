from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy as _

from core.admin import add_short_description
from security.models import (
    BankTransferRecipientDetails,
    BankTransferSenderDetails,
    Check, CHECK_STATUS,
    DebitCardSenderDetails,
    PrisonerProfile,
    RecipientProfile,
    SavedSearch,
    SearchFilter,
    SenderProfile,
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
    inlines = (
        BankTransferSenderDetailsAdminInline,
        DebitCardSenderDetailsAdminInline,
    )
    search_fields = (
        'bank_transfer_details__sender_name',
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

    @add_short_description(_('credit total'))
    def formatted_credit_total(self, instance):
        return format_amount(instance.credit_total)


class BankTransferRecipientDetailsAdminInline(admin.StackedInline):
    model = BankTransferRecipientDetails
    extra = 0


@admin.register(RecipientProfile)
class RecipientProfileAdmin(admin.ModelAdmin):
    ordering = ('-disbursement_count',)
    list_display = ('sort_code', 'account_number', 'disbursement_count', 'formatted_disbursement_total')
    search_fields = (
        'bank_transfer_details__recipient_bank_account__sort_code',
        'bank_transfer_details__recipient_bank_account__account_number',
        'bank_transfer_details__recipient_bank_account__roll_number',
        'disbursements__recipient_first_name',
        'disbursements__recipient_last_name',
    )
    inlines = (BankTransferRecipientDetailsAdminInline,)

    @add_short_description(_('disbursement total'))
    def formatted_disbursement_total(self, instance):
        return format_amount(instance.disbursement_total)

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


@admin.register(PrisonerProfile)
class PrisonerProfileAdmin(admin.ModelAdmin):
    ordering = ('-credit_count',)
    list_display = (
        'prisoner_number', 'credit_count', 'formatted_credit_total',
        'disbursement_count', 'formatted_disbursement_total',
    )
    search_fields = ('prisoner_name', 'prisoner_number', 'prisons__name', 'provided_name__name')
    readonly_fields = ('prisons', 'provided_names',)
    exclude = ('senders', 'recipients',)

    @add_short_description(_('credit total'))
    def formatted_credit_total(self, instance):
        return format_amount(instance.credit_total)

    @add_short_description(_('disbursement total'))
    def formatted_disbursement_total(self, instance):
        return format_amount(instance.disbursement_total)

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


@admin.register(Check)
class CheckAdmin(admin.ModelAdmin):
    ordering = ('-created',)
    list_display = (
        'created',
        'prisoner_name',
        'prisoner_number',
        'status',
        'rules',
        'description',
    )
    list_filter = (
        'status',
    )
    search_fields = (
        'credit__prisoner_name',
        'credit__prisoner_number',
    )
    date_hierarchy = 'created'
    list_select_related = ('credit',)
    exclude = ('credit',)
    readonly_fields = (
        'rules',
        'description',
        'credit_link',
    )
    actions = ['display_stats']

    @add_short_description(_('credit'))
    def credit_link(self, instance):
        credit = instance.credit
        link = reverse('admin:credit_credit_change', args=(credit.pk,))
        description = '%(amount)s %(status)s, %(date)s' % {
            'amount': format_amount(credit.amount),
            'status': credit.resolution,
            'date': format_date(timezone.localtime(credit.created), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)

    def prisoner_name(self, obj):
        return obj.credit.prisoner_name

    def prisoner_number(self, obj):
        return obj.credit.prisoner_number

    @add_short_description(_('Display stats'))
    def display_stats(self, request, queryset):
        self.message_user(request, gettext(
            'FIU have accepted %(accepted_count)s and rejected %(rejected_count)s credits, '
            'with %(pending_count)s still pending.'
        ) % {
            'accepted_count': queryset.filter(status=CHECK_STATUS.ACCEPTED, actioned_by__isnull=False).count(),
            'rejected_count': queryset.filter(status=CHECK_STATUS.REJECTED).count(),
            'pending_count': queryset.filter(status=CHECK_STATUS.PENDING).count(),
        })
