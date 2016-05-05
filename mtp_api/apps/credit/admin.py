from django.contrib import admin

from core.admin import DateRangeFilter, RelatedAnyFieldListFilter, ExactSearchFilter
from payment.models import Payment
from transaction.models import Transaction
from transaction.utils import format_amount
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


@admin.register(Credit)
class CreditAdmin(admin.ModelAdmin):
    list_display = (
        'prisoner_name', 'prison', 'prisoner_number', 'prisoner_dob',
        'formatted_amount', 'created', 'status'
    )
    ordering = ('-created',)
    date_hierarchy = 'created'
    inlines = (TransactionAdminInline, PaymentAdminInline, LogAdminInline)
    readonly_fields = ('resolution', 'reconciled',)
    list_filter = (
        'resolution',
        'reconciled',
        ('prison', RelatedAnyFieldListFilter),
        ('created', DateRangeFilter),
        ('owner__username', ExactSearchFilter),
    )
    search_fields = ('prisoner_name', 'prisoner_number')

    def formatted_amount(self, instance):
        return format_amount(instance.amount)
