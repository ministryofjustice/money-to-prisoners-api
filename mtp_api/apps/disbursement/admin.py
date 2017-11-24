from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from core.admin import add_short_description
from disbursement.models import Disbursement, Recipient
from transaction.utils import format_amount


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = (
        'created', 'formatted_amount', 'prisoner_number', 'prison', 'resolution',
        'method'
    )
    date_hierarchy = 'created'
    exclude = ('recipient',)
    readonly_fields = ('recipient_link',)

    @classmethod
    def formatted_amount(cls, instance):
        return format_amount(instance.amount)

    @add_short_description('recipient')
    def recipient_link(self, instance):
        link = reverse(
            'admin:disbursement_recipient_change', args=(instance.recipient.pk,)
        )
        return format_html('<a href="{}">{}</a>', link, instance.recipient)


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'postcode', 'sort_code', 'account_number')
