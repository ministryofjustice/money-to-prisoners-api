from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import add_short_description
from disbursement.models import Disbursement, Log
from transaction.utils import format_amount


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


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = (
        'recipient_name', 'formatted_amount', 'prisoner_number',
        'prison', 'resolution', 'method', 'created'
    )
    inlines = (LogAdminInline,)
    date_hierarchy = 'created'

    @add_short_description(_('amount'))
    def formatted_amount(self, instance):
        return format_amount(instance.amount)
