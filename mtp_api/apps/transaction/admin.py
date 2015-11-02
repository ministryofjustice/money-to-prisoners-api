from django.contrib import admin
from django.contrib.admin import ModelAdmin

from .models import Transaction


class TransactionAdmin(ModelAdmin):
    list_display = ('prisoner_name', 'prisoner_number', 'formatted_amount', 'sender_name',
                    'received_at', 'credited_at', 'refunded_at')
    ordering = ('-received_at',)

    @classmethod
    def formatted_amount(cls, instance):
        return '£%0.2f' % (instance.amount / 100)


admin.site.register(Transaction, TransactionAdmin)
