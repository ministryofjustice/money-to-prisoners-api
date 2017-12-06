from django.contrib import admin

from disbursement.models import Disbursement
from transaction.utils import format_amount


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = (
        'recipient_name', 'formatted_amount', 'prisoner_number',
        'prison', 'resolution', 'method', 'created'
    )
    date_hierarchy = 'created'

    @classmethod
    def formatted_amount(cls, instance):
        return format_amount(instance.amount)
