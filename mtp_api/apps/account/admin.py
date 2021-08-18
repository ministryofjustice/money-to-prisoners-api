from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from mtp_common.utils import format_currency

from account.models import Balance
from core.admin import add_short_description


@admin.register(Balance)
class BalanceAdmin(admin.ModelAdmin):
    list_display = ('date', 'balance')
    date_hierarchy = 'date'

    @add_short_description(_('balance'))
    def balance(self, instance):
        return format_currency(instance.closing_balance)
