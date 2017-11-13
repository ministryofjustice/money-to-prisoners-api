from django.contrib import admin

from disbursement.models import Disbursement, Recipient
from transaction.utils import format_amount


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = (
        'created', 'formatted_amount', 'prisoner_number', 'prison', 'resolution',
        'method'
    )
    date_hierarchy = 'created'

    @classmethod
    def formatted_amount(cls, instance):
        return format_amount(instance.amount)


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'postcode', 'sort_code', 'account_number')
