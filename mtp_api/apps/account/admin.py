from django.contrib import admin

from account.models import Batch, Balance
from transaction.utils import format_amount


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('created', 'label', 'user', 'transaction_count')

    @classmethod
    def transaction_count(cls, instance):
        return instance.transactions.count()


@admin.register(Balance)
class BalanceAdmin(admin.ModelAdmin):
    list_display = ('date', 'balance')
    date_hierarchy = 'date'

    @classmethod
    def balance(cls, instance):
        return format_amount(instance.closing_balance)
