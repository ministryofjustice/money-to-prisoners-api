from django.contrib import admin

from account.models import Balance
from transaction.utils import format_amount


@admin.register(Balance)
class BalanceAdmin(admin.ModelAdmin):
    list_display = ('date', 'balance')
    date_hierarchy = 'date'

    @classmethod
    def balance(cls, instance):
        return format_amount(instance.closing_balance)
