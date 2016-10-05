from django.contrib import admin
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from payment.models import Payment
from transaction.utils import format_amount


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('created', 'status',
                    'formatted_amount', 'formatted_service_charge')
    ordering = ('-created',)
    date_hierarchy = 'created'
    exclude = ('credit',)
    readonly_fields = ('credit_link',)

    def credit_link(self, instance):
        link = reverse('admin:credit_credit_change', args=(instance.credit.pk,))
        description = '%(amount)s %(status)s, %(date)s' % {
            'amount': format_amount(instance.amount),
            'status': instance.status,
            'date': format_date(timezone.localtime(instance.created), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)

    def formatted_amount(self, instance):
        return format_amount(instance.amount)

    def formatted_service_charge(self, instance):
        return format_amount(instance.service_charge)

    credit_link.short_description = _('Credit')
    formatted_amount.short_description = _('Amount')
    formatted_service_charge.short_description = _('Service charge')
