from django.contrib import admin
from django.core.urlresolvers import reverse
from django.db import models
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from core.admin import add_short_description
from payment.models import Batch, Payment
from transaction.utils import format_amount


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('date', 'payment_count', 'payment_amount', 'ref_code', 'settled',)
    date_hierarchy = 'date'
    exclude = ('settlement_transaction',)
    readonly_fields = ('payment_link', 'payment_count', 'payment_amount', 'settlement_link',)

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
    def payment_amount(self, instance):
        return format_amount(
            instance.payment_set.aggregate(total_amount=models.Sum('amount'))['total_amount']
        )

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
            'amount': format_amount(settlement.amount),
            'date': format_date(timezone.localtime(settlement.received_at), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('created', 'status',
                    'formatted_amount', 'formatted_service_charge')
    ordering = ('-created',)
    date_hierarchy = 'created'
    list_filter = ('status',)
    search_fields = ('uuid', 'recipient_name')
    exclude = ('credit',)
    readonly_fields = ('credit_link',)
    actions = ['display_total_amount']

    @add_short_description(_('credit'))
    def credit_link(self, instance):
        link = reverse('admin:credit_credit_change', args=(instance.credit.pk,))
        description = '%(amount)s %(status)s, %(date)s' % {
            'amount': format_amount(instance.amount),
            'status': instance.status,
            'date': format_date(timezone.localtime(instance.created), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)

    @add_short_description(_('amount'))
    def formatted_amount(self, instance):
        return format_amount(instance.amount)

    @add_short_description(_('service charge'))
    def formatted_service_charge(self, instance):
        return format_amount(instance.service_charge)

    @add_short_description(_('Display total of selected payments'))
    def display_total_amount(self, request, queryset):
        total = queryset.aggregate(models.Sum('amount'))['amount__sum']
        self.message_user(request, _('Total: %s') % format_amount(total, True))
