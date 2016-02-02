from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.db.models import Sum

from core.admin import DateRangeFilter, RelatedAnyFieldListFilter, ExactSearchFilter
from .models import Transaction, Log, LOG_ACTIONS


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


class TransactionAdmin(admin.ModelAdmin):
    list_display = ('prisoner_name', 'prisoner_number', 'prison', 'formatted_amount',
                    'sender_name', 'received_at', 'credited_at', 'refunded_at')
    ordering = ('-received_at',)
    readonly_fields = ('credited', 'refunded', 'reconciled')
    inlines = (LogAdminInline,)
    list_filter = (
        'credited',
        'refunded',
        'reconciled',
        ('prison', RelatedAnyFieldListFilter),
        'category',
        'source',
        ('received_at', DateRangeFilter),
        ('owner__username', ExactSearchFilter)
    )
    actions = [
        'display_total_amount', 'display_reference_validity',
        'display_resolution_time'
    ]

    @classmethod
    def formatted_amount(cls, instance):
        return '£%0.2f' % (instance.amount / 100)

    def display_total_amount(self, request, queryset):
        total = queryset.aggregate(Sum('amount'))['amount__sum']
        self.message_user(request, 'Total: £%0.2f' % (total / 100))

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


admin.site.register(Transaction, TransactionAdmin)
