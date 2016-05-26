from django.contrib import admin
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import ValidationError

from core.admin import DateRangeFilter
from transaction.constants import TRANSACTION_STATUS
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
        'type', 'sender_sort_code', 'sender_account_number',
        'sender_roll_number', 'sender_name', 'reference',
        'received_at', 'status'
    )
    ordering = ('-received_at',)
    date_hierarchy = 'received_at'
    readonly_fields = ('incomplete_sender_info', 'reference_in_sender_field')
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

    def formatted_amount(self, instance):
        return format_amount(instance.amount)
    formatted_amount.short_description = 'Amount'

    def type(self, instance):
        return '%s/%s' % (instance.processor_type_code, instance.category)
