from django.contrib import admin
from django.db.models import Sum

from core.admin import DateRangeFilter, RelatedAnyFieldListFilter
from .models import Transaction, Log


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
    list_filter = ('credited', 'refunded', 'reconciled',
                   ('prison', RelatedAnyFieldListFilter),
                   ('received_at', DateRangeFilter))
    actions = ['display_total_amount', 'display_reference_validity']

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


admin.site.register(Transaction, TransactionAdmin)
