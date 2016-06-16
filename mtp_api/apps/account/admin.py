from django.contrib import admin
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from account.models import Batch, Balance
from transaction.constants import TRANSACTION_CATEGORY
from transaction.utils import format_amount


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('created', 'label', 'user', 'transaction_count')
    exclude = ('transactions',)
    readonly_fields = ('label', 'list_transactions', 'user')

    @classmethod
    def transaction_count(cls, instance):
        return instance.transactions.count()

    def list_transactions(self, instance):
        def mapper(transaction):
            params = {
                'amount': format_amount(transaction.amount),
                'date': format_date(timezone.localtime(transaction.received_at), 'd/m/Y'),
            }
            if transaction.category == TRANSACTION_CATEGORY.CREDIT:
                params['status'] = 'credit (%s)' % transaction.status
            else:
                params['status'] = 'debit'
            return (
                reverse('admin:transaction_transaction_change', args=(transaction.id,)),
                '%(amount)s %(status)s, %(date)s' % params,
            )

        return format_html_join(mark_safe('<br>\n'), '<a href="{}">{}</a>', (
            mapper(transaction)
            for transaction in instance.transactions.all()
        ))

    list_transactions.short_description = _('Transactions')


@admin.register(Balance)
class BalanceAdmin(admin.ModelAdmin):
    list_display = ('date', 'balance')
    date_hierarchy = 'date'

    @classmethod
    def balance(cls, instance):
        return format_amount(instance.closing_balance)
