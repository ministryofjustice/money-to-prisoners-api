from django.contrib import admin

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
    list_display = ('prisoner_name', 'prisoner_number', 'formatted_amount', 'sender_name',
                    'received_at', 'credited_at', 'refunded_at')
    ordering = ('-received_at',)
    readonly_fields = ('credited', 'refunded')
    inlines = (LogAdminInline,)
    list_filter = ('credited', 'refunded',
                   ('prison', RelatedAnyFieldListFilter),
                   ('received_at', DateRangeFilter))
    actions = ['display_total_amount', 'display_reference_validity']

    @classmethod
    def formatted_amount(cls, instance):
        return '£%0.2f' % (instance.amount / 100)

    def display_total_amount(self, request, queryset):
        total = sum(map(lambda t: t.amount, queryset))
        self.message_user(request, 'Total: £%0.2f' % (total / 100))

    def display_reference_validity(self, request, queryset):
        invalid_ref_count = len(list(filter(lambda t: t.prison is None, queryset)))
        invalid_percent = (invalid_ref_count / len(queryset)) * 100

        valid_ref_count = len(queryset) - invalid_ref_count
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
