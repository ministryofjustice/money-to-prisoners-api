from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from core.admin import DateRangeFilter, add_short_description
from transaction.constants import TRANSACTION_CATEGORY, TRANSACTION_STATUS
from transaction.models import Transaction
from transaction.utils import format_amount


class StatusFilter(admin.SimpleListFilter):
    parameter_name = 'status'
    title = _('status')

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
    actions = ['display_total_amount']

    @add_short_description(_('credit'))
    def credit_link(self, instance):
        if instance.credit is None:
            return '–'
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

    @add_short_description(_('type'))
    def transaction_type(self, instance):
        category = instance.category
        if TRANSACTION_CATEGORY.has_value(category):
            category = TRANSACTION_CATEGORY.for_value(category).display
        return '%s/%s' % (instance.processor_type_code, category)

    @add_short_description(_('status'))
    def formatted_status(self, instance):
        value = instance.status
        if TRANSACTION_STATUS.has_value(value):
            return TRANSACTION_STATUS.for_value(value).display
        return value

    @add_short_description(_('Display total of selected transactions'))
    def display_total_amount(self, request, queryset):
        total = queryset.aggregate(models.Sum('amount'))['amount__sum']
        self.message_user(request, _('Total: %s') % format_amount(total, True))
