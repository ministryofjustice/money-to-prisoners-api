from django.contrib import admin
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from mtp_common.utils import format_currency

from core.admin import add_short_description
from payment.models import Batch, BillingAddress, Payment


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = (
        'date', 'payment_count', 'formatted_payment_amount', 'ref_code', 'settled',
    )
    date_hierarchy = 'date'
    exclude = ('settlement_transaction',)
    readonly_fields = (
        'payment_link', 'payment_count', 'formatted_payment_amount', 'settlement_link',
    )

    @add_short_description(_('payment set'))
    def payment_link(self, instance):
        link = reverse('admin:payment_payment_changelist')
        return format_html(
            '<a href="{}?batch_id={}">{}</a>',
            link, instance.pk, 'Payments'
        )

    @add_short_description(_('payment count'))
    def payment_count(self, instance):
        return instance.payment_set.count()

    @add_short_description(_('payment amount'))
    def formatted_payment_amount(self, instance):
        return format_currency(instance.payment_amount)

    @add_short_description(_('settled?'))
    def settled(self, instance):
        return instance.settlement_transaction is not None

    @add_short_description(_('settlement transaction'))
    def settlement_link(self, instance):
        settlement = instance.settlement_transaction
        if settlement is None:
            return '–'
        link = reverse('admin:transaction_transaction_change', args=(settlement.pk,))
        description = '%(amount)s, %(date)s' % {
            'amount': format_currency(settlement.amount),
            'date': format_date(timezone.localtime(settlement.received_at), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)


@admin.register(BillingAddress)
class BillingAddressAdmin(admin.ModelAdmin):
    list_display = ('line1', 'line2', 'city', 'country', 'postcode')
    search_fields = ('postcode',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('cardholder_name', 'email', 'formatted_amount', 'status', 'created')
    ordering = ('-created',)
    date_hierarchy = 'created'
    list_filter = ('status',)
    search_fields = ('uuid', 'recipient_name', 'email', 'card_number_last_digits',)
    exclude = ('credit', 'billing_address',)
    readonly_fields = ('credit_link', 'batch', 'billing_address_link',)
    actions = ['display_total_amount']

    @add_short_description(_('credit'))
    def credit_link(self, instance):
        link = reverse('admin:credit_credit_change', args=(instance.credit.pk,))
        description = '%(amount)s %(status)s, %(date)s' % {
            'amount': format_currency(instance.amount),
            'status': instance.credit.resolution,
            'date': format_date(timezone.localtime(instance.credit.created), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)

    @add_short_description(_('billing address'))
    def billing_address_link(self, instance):
        link = reverse('admin:payment_billingaddress_change', args=(instance.billing_address.pk,))
        return format_html('<a href="{}">{}</a>', link, str(instance.billing_address))

    @add_short_description(_('amount'))
    def formatted_amount(self, instance):
        return format_currency(instance.amount)

    @add_short_description(_('service charge'))
    def formatted_service_charge(self, instance):
        return format_currency(instance.service_charge)

    @add_short_description(_('Display total of selected payments'))
    def display_total_amount(self, request, queryset):
        total = queryset.aggregate(models.Sum('amount'))['amount__sum']
        self.message_user(request, _('Total: %s') % format_currency(total, trim_empty_pence=True))
