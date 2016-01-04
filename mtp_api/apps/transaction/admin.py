from django.contrib import admin

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
    list_filter = ('credited', 'refunded', 'prison')

    @classmethod
    def formatted_amount(cls, instance):
        return '£%0.2f' % (instance.amount / 100)


admin.site.register(Transaction, TransactionAdmin)
