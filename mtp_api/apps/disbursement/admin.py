from django.contrib import admin
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.admin import add_short_description
from disbursement.models import Disbursement, Log, Comment
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


class CommentAdminInline(admin.StackedInline):
    model = Comment
    extra = 0
    readonly_fields = ('disbursement',)


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = (
        'recipient_name', 'formatted_amount', 'prisoner_number',
        'prison', 'resolution', 'method', 'created'
    )
    list_filter = ('resolution', 'method', 'prison')
    search_fields = ('prisoner_name', 'prisoner_number')
    inlines = (LogAdminInline, CommentAdminInline,)
    date_hierarchy = 'created'
    actions = ['display_total_amount']

    @add_short_description(_('amount'))
    def formatted_amount(self, instance):
        return format_amount(instance.amount)

    @add_short_description(_('Display total of selected disbursements'))
    def display_total_amount(self, request, queryset):
        total = queryset.aggregate(models.Sum('amount'))['amount__sum']
        self.message_user(request, _('Total: %s') % format_amount(total, True))


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('comment', 'user', 'disbursement',)
    readonly_fields = ('disbursement',)
