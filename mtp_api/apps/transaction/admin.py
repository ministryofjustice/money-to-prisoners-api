from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import ValidationError
from django.db.models import Sum

from core.admin import DateRangeFilter, RelatedAnyFieldListFilter, ExactSearchFilter
from transaction.constants import TRANSACTION_STATUS
from transaction.models import Transaction, Log, LOG_ACTIONS
from transaction.utils import format_amount


class LogAdminInline(admin.TabularInline):
    model = Log
    extra = 0
    fields = ('action', 'created', 'user')
    readonly_fields = ('action', 'created', 'user')
    ordering = ('-created',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StatusFilter(admin.SimpleListFilter):
    parameter_name = 'status'
    title = 'status'

    def lookups(self, request, model_admin):
        return TRANSACTION_STATUS

    def queryset(self, request, queryset):
        status = self.used_parameters.get(self.parameter_name)
        if status in Transaction.STATUS_LOOKUP:
            try:
                return queryset.filter(**Transaction.STATUS_LOOKUP[status])
            except ValidationError as e:
                raise IncorrectLookupParameters(e)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'prisoner_name', 'prisoner_number', 'prison', 'formatted_amount',
        'type', 'sender_sort_code', 'sender_account_number',
        'sender_roll_number', 'sender_name', 'reference',
        'received_at', 'status'
    )
    ordering = ('-received_at',)
    date_hierarchy = 'received_at'
    readonly_fields = (
        'credited', 'refunded', 'reconciled', 'incomplete_sender_info',
        'reference_in_sender_field'
    )
    inlines = (LogAdminInline,)
    list_filter = (
        StatusFilter,
        'reconciled',
        ('prison', RelatedAnyFieldListFilter),
        'category',
        'source',
        ('received_at', DateRangeFilter),
        ('owner__username', ExactSearchFilter),
        'reference_in_sender_field'
    )
    search_fields = ('prisoner_name', 'prisoner_number', 'reference',
                     'sender_name', 'sender_sort_code', 'sender_account_number', 'sender_roll_number')
    actions = [
        'display_total_amount', 'display_reference_validity',
        'display_resolution_time'
    ]

    def formatted_amount(self, instance):
        return format_amount(instance.amount)

    formatted_amount.short_description = 'Amount'

    def type(self, instance):
        return '%s/%s' % (instance.processor_type_code, instance.category)

    def display_total_amount(self, request, queryset):
        total = queryset.aggregate(Sum('amount'))['amount__sum']
        self.message_user(request, 'Total: %s' % format_amount(total, True))

    def display_reference_validity(self, request, queryset):
        invalid_ref_count = queryset.filter(prison__isnull=True).count()
        invalid_percent = (invalid_ref_count / queryset.count()) * 100

        valid_ref_count = queryset.count() - invalid_ref_count
        valid_percent = 100 - invalid_percent

        self.message_user(
            request,
            'Of %(total)s transactions: '
            '%(valid_count)s (%(valid_percent)0.2f%%) of references are valid, '
            '%(invalid_count)s (%(invalid_percent)0.2f%%) of references are invalid.'
            % {'total': len(queryset), 'invalid_count': invalid_ref_count,
               'invalid_percent': invalid_percent, 'valid_count': valid_ref_count,
               'valid_percent': valid_percent}
        )

    def display_resolution_time(self, request, queryset):
        until_credited_times = []
        until_unlocked_times = []
        for t in queryset.prefetch_related('log_set'):
            last_lock_time = None
            logs = sorted(t.log_set.all(), key=lambda l: l.created)
            for l in logs:
                if l.action == LOG_ACTIONS.LOCKED:
                    last_lock_time = l.created
                elif l.action == LOG_ACTIONS.UNLOCKED:
                    if last_lock_time is not None:
                        until_unlocked_times.append(l.created - last_lock_time)
                elif l.action == LOG_ACTIONS.CREDITED:
                    if last_lock_time is not None:
                        until_credited_times.append(l.created - last_lock_time)

        if until_credited_times:
            avg_credit_time = (sum(until_credited_times, timedelta(0)) /
                               len(until_credited_times))

            self.message_user(
                request,
                'Time until credit after lock: '
                'AVG (%(avg)s), MAX (%(max)s), MIN (%(min)s)'
                % {'avg': avg_credit_time, 'max': max(until_credited_times),
                   'min': min(until_credited_times)}
            )
        else:
            self.message_user(request, 'No transactions have been credited yet.',
                              messages.WARNING)

        if until_unlocked_times:
            avg_unlock_time = (sum(until_unlocked_times, timedelta(0)) /
                               len(until_unlocked_times))

            self.message_user(
                request,
                'Time until unlock after lock: '
                'AVG (%(avg)s), MAX (%(max)s), MIN (%(min)s)'
                % {'avg': avg_unlock_time, 'max': max(until_unlocked_times),
                   'min': min(until_unlocked_times)}
            )
        else:
            self.message_user(request, 'No transactions have been unlocked yet.',
                              messages.WARNING)
