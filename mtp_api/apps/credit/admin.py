from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

from core.admin import DateRangeFilter, RelatedAnyFieldListFilter, ExactSearchFilter
from payment.models import Payment
from transaction.models import Transaction
from transaction.utils import format_amount
from .constants import CREDIT_STATUS, LOG_ACTIONS
from .models import Credit, Log


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


class TransactionAdminInline(admin.StackedInline):
    model = Transaction
    extra = 0
    readonly_fields = ('incomplete_sender_info', 'reference_in_sender_field')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PaymentAdminInline(admin.StackedInline):
    model = Payment
    extra = 0
    readonly_fields = ('uuid', 'status',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StatusFilter(admin.SimpleListFilter):
    parameter_name = 'status'
    title = _('status')

    def lookups(self, request, model_admin):
        return CREDIT_STATUS

    def queryset(self, request, queryset):
        status = self.used_parameters.get(self.parameter_name)
        if status in Credit.STATUS_LOOKUP:
            try:
                return queryset.filter(Credit.STATUS_LOOKUP[status])
            except ValidationError as e:
                raise IncorrectLookupParameters(e)


@admin.register(Credit)
class CreditAdmin(admin.ModelAdmin):
    list_display = (
        'prisoner_name', 'prison', 'prisoner_number', 'prisoner_dob',
        'formatted_amount', 'source', 'received_at', 'status'
    )
    ordering = ('-received_at',)
    date_hierarchy = 'received_at'
    inlines = (TransactionAdminInline, PaymentAdminInline, LogAdminInline)
    readonly_fields = ('resolution', 'reconciled',)
    list_filter = (
        StatusFilter,
        'resolution',
        'reconciled',
        ('prison', RelatedAnyFieldListFilter),
        ('received_at', DateRangeFilter),
        ('owner__username', ExactSearchFilter),
    )
    search_fields = ('prisoner_name', 'prisoner_number')
    actions = [
        'display_total_amount', 'display_credit_validity',
        'display_resolution_time'
    ]

    def formatted_amount(self, instance):
        return format_amount(instance.amount)

    formatted_amount.short_description = _('Amount')

    def display_total_amount(self, request, queryset):
        total = queryset.aggregate(Sum('amount'))['amount__sum']
        self.message_user(request, _('Total: %s') % format_amount(total, True))

    def display_credit_validity(self, request, queryset):
        invalid_ref_count = queryset.filter(prison__isnull=True).count()
        total_count = queryset.count()
        invalid_percent = (invalid_ref_count / total_count) * 100

        valid_ref_count = total_count - invalid_ref_count
        valid_percent = 100 - invalid_percent

        self.message_user(
            request,
            _('Of %(total)s credits: '
              '%(valid_count)s (%(valid_percent)0.2f%%) can be credited to a prisoner, '
              '%(invalid_count)s (%(invalid_percent)0.2f%%) cannot be credited.')
            % {'total': total_count, 'invalid_count': invalid_ref_count,
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
                _('Time until credit after lock: '
                  'AVG (%(avg)s), MAX (%(max)s), MIN (%(min)s)')
                % {'avg': avg_credit_time, 'max': max(until_credited_times),
                   'min': min(until_credited_times)}
            )
        else:
            self.message_user(request, _('No credits have been credited yet.'),
                              messages.WARNING)

        if until_unlocked_times:
            avg_unlock_time = (sum(until_unlocked_times, timedelta(0)) /
                               len(until_unlocked_times))

            self.message_user(
                request,
                _('Time until unlock after lock: '
                  'AVG (%(avg)s), MAX (%(max)s), MIN (%(min)s)')
                % {'avg': avg_unlock_time, 'max': max(until_unlocked_times),
                   'min': min(until_unlocked_times)}
            )
        else:
            self.message_user(request, _('No credits have been unlocked yet.'),
                              messages.WARNING)
