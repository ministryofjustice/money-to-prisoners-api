from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from core.admin import DateRangeFilter
from transaction.constants import TRANSACTION_CATEGORY, TRANSACTION_STATUS
from transaction.models import Transaction
from transaction.utils import format_amount


class StatusFilter(admin.SimpleListFilter):
    parameter_name = 'status'
    title = 'status'

    def lookups(self, request, model_admin):
        return TRANSACTION_STATUS

    def queryset(self, request, queryset):
        status = self.used_parameters.get(self.parameter_name)
        if status in Transaction.STATUS_LOOKUP:
            try:
                return queryset.filter(Transaction.STATUS_LOOKUP[status])
            except ValidationError as e:
                raise IncorrectLookupParameters(e)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'prisoner_name', 'prison', 'prisoner_number', 'formatted_amount',
        'transaction_type', 'sender_sort_code', 'sender_account_number',
        'sender_roll_number', 'sender_name', 'reference',
        'received_at', 'formatted_status',
    )
    ordering = ('-received_at',)
    date_hierarchy = 'received_at'
    list_filter = (
        StatusFilter,
        'category',
        'source',
        ('received_at', DateRangeFilter),
        'reference_in_sender_field'
    )
    search_fields = (
        'reference', 'sender_name', 'sender_sort_code',
        'sender_account_number', 'sender_roll_number'
    )
    exclude = ('credit',)
    readonly_fields = ('credit_link', 'incomplete_sender_info', 'reference_in_sender_field')

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

    def transaction_type(self, instance):
        category = instance.category
        if TRANSACTION_CATEGORY.has_value(category):
            category = TRANSACTION_CATEGORY.for_value(category).display
        return '%s/%s' % (instance.processor_type_code, category)

    def formatted_status(self, instance):
        value = instance.status
        if TRANSACTION_STATUS.has_value(value):
            return TRANSACTION_STATUS.for_value(value).display
        return value

    formatted_status.short_description = _('Status')

    credit_link.short_description = _('Credit')
    formatted_amount.short_description = _('Amount')
    transaction_type.short_description = _('Type')
