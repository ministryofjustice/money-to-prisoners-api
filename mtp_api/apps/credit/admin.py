from datetime import timedelta

from django.contrib import admin
from django.contrib import messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from mtp_common.utils import format_currency

from core.admin import (
    UtcDateRangeFilter, RelatedAnyFieldListFilter, SearchFilter,
    add_short_description
)
from credit.constants import CREDIT_SOURCE, CREDIT_STATUS, LOG_ACTIONS
from credit.models import Credit, Log, Comment, ProcessingBatch, PrivateEstateBatch
from payment.models import Payment
from transaction.models import Transaction


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


class CommentAdminInline(admin.StackedInline):
    model = Comment
    extra = 0
    readonly_fields = ('credit',)


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
    readonly_fields = ('uuid', 'status', 'batch', 'billing_address',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StatusFilter(admin.SimpleListFilter):
    parameter_name = 'status'
    title = _('status')

    def lookups(self, request, model_admin):
        return CREDIT_STATUS.choices

    def queryset(self, request, queryset):
        status = self.used_parameters.get(self.parameter_name)
        if status in Credit.STATUS_LOOKUP:
            try:
                return queryset.filter(Credit.STATUS_LOOKUP[status])
            except ValidationError as e:
                raise IncorrectLookupParameters(e)


class SourceFilter(admin.SimpleListFilter):
    parameter_name = 'source'
    title = _('source')

    def lookups(self, request, model_admin):
        return CREDIT_SOURCE.choices

    def queryset(self, request, queryset):
        source = self.used_parameters.get(self.parameter_name)
        if source in CREDIT_SOURCE:
            try:
                if source == CREDIT_SOURCE.BANK_TRANSFER:
                    return queryset.filter(transaction__isnull=False)
                elif source == CREDIT_SOURCE.ONLINE:
                    return queryset.filter(payment__isnull=False)
                else:
                    return queryset.filter(payment__isnull=True, transaction__isnull=True)
            except ValidationError as e:
                raise IncorrectLookupParameters(e)


@admin.register(Credit)
class CreditAdmin(admin.ModelAdmin):
    list_display = (
        'prisoner_name', 'prison', 'prisoner_number', 'prisoner_dob',
        'formatted_amount', 'received_at', 'formatted_source', 'formatted_status'
    )
    ordering = ('-received_at',)
    date_hierarchy = 'received_at'
    inlines = (TransactionAdminInline, PaymentAdminInline, CommentAdminInline, LogAdminInline)
    readonly_fields = (
        'resolution',
        'reconciled',
        'reviewed',
        'blocked',
        'sender_profile',
        'prisoner_profile',
        'owner',
        'private_estate_batch',
    )
    list_filter = (
        StatusFilter,
        SourceFilter,
        'resolution',
        ('prison', RelatedAnyFieldListFilter),
        ('received_at', UtcDateRangeFilter),
        'reconciled',
        'reviewed',
        ('owner__username', SearchFilter),
    )
    search_fields = ('prisoner_name', 'prisoner_number')
    actions = [
        'display_total_amount', 'display_credit_validity',
        'display_resolution_time'
    ]

    def get_queryset(self, request):
        qs = Credit.objects_all.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    @add_short_description(_('amount'))
    def formatted_amount(self, instance):
        return format_currency(instance.amount)

    @add_short_description(_('source'))
    def formatted_source(self, instance):
        value = instance.source
        if value in CREDIT_SOURCE.values:
            return dict(CREDIT_SOURCE.choices)[value]
        return value

    @add_short_description(_('status'))
    def formatted_status(self, instance):
        value = instance.status
        if value in CREDIT_STATUS.values:
            return dict(CREDIT_STATUS.choices)[value]
        return value

    @add_short_description(_('Display total of selected credits'))
    def display_total_amount(self, request, queryset):
        total = queryset.aggregate(Sum('amount'))['amount__sum']
        self.message_user(request, _('Total: %s') % format_currency(total, trim_empty_pence=True))

    @add_short_description(_('Display credit validity of selected credits'))
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

    @add_short_description(_('Display resolution time of selected credits'))
    def display_resolution_time(self, request, queryset):
        until_credited_times = []
        for credit in queryset.prefetch_related('log_set'):
            logs = sorted(credit.log_set.all(), key=lambda log: log.created)
            for log in logs:
                if log.action == LOG_ACTIONS.CREDITED:
                    until_credited_times.append(log.created - credit.received_at)

        if until_credited_times:
            avg_credit_time = (sum(until_credited_times, timedelta(0)) /
                               len(until_credited_times))

            self.message_user(
                request,
                _('Time until credit after being received: average %(avg)s, maximum %(max)s, minimum %(min)s') % {
                    'avg': avg_credit_time,
                    'max': max(until_credited_times),
                    'min': min(until_credited_times),
                }
            )
        else:
            self.message_user(request, _('No credits have been credited yet.'),
                              messages.WARNING)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('comment', 'user', 'credit',)
    readonly_fields = ('credit',)


@admin.register(ProcessingBatch)
class ProcessingBatchAdmin(admin.ModelAdmin):
    list_display = ('created', 'user', 'credit_count',)

    def credit_count(self, instance):
        return len(instance.credits.all())


@admin.register(PrivateEstateBatch)
class PrivateEstateBatchAdmin(admin.ModelAdmin):
    list_display = ('date', 'prison', 'total_amount',)
    list_filter = ('prison',)
    date_hierarchy = 'date'

    @add_short_description(_('amount'))
    def total_amount(self, instance):
        return format_currency(instance.total_amount)
