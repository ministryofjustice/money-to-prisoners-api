import datetime
from functools import reduce
import re

from django import forms
from django.core.urlresolvers import reverse
from django.db import models
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from account.models import Balance
from core.dashboards import DashboardModule
from core.views import DashboardView
from transaction.constants import TRANSACTION_CATEGORY, TRANSACTION_SOURCE, TRANSACTION_STATUS
from transaction.models import Transaction
from transaction.utils import format_amount, format_number

CREDITABLE_FILTERS = {
    'prison__isnull': False,
    'category': TRANSACTION_CATEGORY.CREDIT,
    'source__in': [
        TRANSACTION_SOURCE.BANK_TRANSFER,
        TRANSACTION_SOURCE.ONLINE,
    ],
}
CREDITED_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITED]
REFUNDABLE_FILTERS = {
    'prison__isnull': True,
    'incomplete_sender_info': False,
    'category': TRANSACTION_CATEGORY.CREDIT,
    'source': TRANSACTION_SOURCE.BANK_TRANSFER,
}
REFUNDED_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.REFUNDED]
UNIDENTIFIED_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.UNIDENTIFIED]


class TransactionReportDateForm(forms.Form):
    date_range = forms.ChoiceField(
        label=_('Date range'),
        choices=(
            ('latest', _('Latest')),
            ('this_month', _('This month')),
            ('all', _('Since the beginning')),
        ),
        initial='latest',
    )


class TransactionReportChart:
    def __init__(self, queryset, start_date=None, end_date=None):
        self.queryset = queryset
        self.start_date = start_date or \
            timezone.localtime(self.queryset.earliest().received_at).date()
        self.end_date = end_date or \
            timezone.localtime(self.queryset.latest().received_at).date()

    @property
    def data(self):
        columns = '[%s]' % ','.join(
            '{type: "%s", title: "%s"}' % (
                column['type'],
                force_text(column['title']),
            )
            for column in self.columns
        )
        rows = '[%s]' % ','.join(
            '[new Date(%d,%d,%d),%d,%d]' % (
                date.year, date.month - 1, date.day,
                creditable, refundable,
            )
            for date, creditable, refundable in self.rows
        )
        return mark_safe('{columns: %s, rows: %s}' % (columns, rows))

    @property
    def columns(self):
        return [
            {'type': 'date', 'title': _('Date')},
            {'type': 'number', 'title': _('Valid credits')},
            {'type': 'number', 'title': _('Credits to refund')},
        ]

    @property
    def rows(self):
        days = (self.end_date - self.start_date).days
        if days > 100:
            date_stride = days // 100
        else:
            date_stride = 1
        date_stride = datetime.timedelta(days=date_stride)

        date = self.start_date
        while date <= self.end_date:
            transactions = self.queryset.filter(received_at__date=date)
            creditable = transactions.filter(**CREDITABLE_FILTERS).count() or 0
            refundable = transactions.filter(**REFUNDABLE_FILTERS).count() or 0
            yield [date, creditable, refundable]
            date += date_stride


@DashboardView.register_dashboard
class TransactionReport(DashboardModule):
    template = 'core/dashboard/transaction-report.html'
    column_count = 3
    title = _('Transaction report')
    show_stand_out = True
    priority = 100
    cookie_key = 'transaction-report'

    class Media:
        css = {
            'all': ('core/css/transaction-report.css',)
        }
        js = (
            'https://www.gstatic.com/charts/loader.js',
            'core/js/transaction-report.js',
        )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.form = TransactionReportDateForm(data=self.cookie_data)
        date_range = self.form['date_range'].value()
        if date_range == 'all':
            self.title = _('All transactions')
            self.queryset = Transaction.objects.all()
            filter_string = ''
            self.chart = TransactionReportChart(self.queryset)
        elif date_range == 'this_month':
            received_at_end = timezone.localtime(timezone.now()).date()
            received_at_start = received_at_end.replace(day=1)
            self.title = _('Transactions received in %(month)s') % {
                'month': format_date(received_at_start, 'N Y')
            }
            self.queryset = Transaction.objects.filter(
                received_at__date__gte=received_at_start,
                received_at__date__lte=received_at_end,
            )
            filter_string = 'received_at__date__gte=%s&' \
                            'received_at__date__lte=%s' % (received_at_start.isoformat(),
                                                           received_at_end.isoformat())
            self.chart = TransactionReportChart(
                self.queryset,
                start_date=received_at_start,
                end_date=received_at_end,
            )
        else:
            try:
                received_at = timezone.localtime(Transaction.objects.latest().received_at).date()
            except Transaction.DoesNotExist:
                received_at = (timezone.localtime(timezone.now()) - datetime.timedelta(days=1)).date()
            self.title = _('Latest transactions received on %(date)s') % {
                'date':  format_date(received_at, 'j N')
            }
            self.queryset = Transaction.objects.filter(
                received_at__date=received_at,
            )
            filter_string = 'received_at__day=%d&' \
                            'received_at__month=%d&' \
                            'received_at__year=%d' % (received_at.day,
                                                      received_at.month,
                                                      received_at.year)
            self.chart = None

        if self.dashboard_view and self.dashboard_view.request.user.has_perm('transaction.change_transaction'):
            self.change_list_url = reverse('admin:transaction_transaction_changelist') + '?' + filter_string

    @classmethod
    def get_current_balance(cls):
        value = getattr(Balance.objects.first(), 'closing_balance', None)
        return format_amount(value, trim_empty_pence=True) or '—'

    @classmethod
    def get_count(cls, queryset):
        value = queryset.count()
        if value is None:
            return '—'
        if isinstance(value, (int, float)):
            return format_number(value)
        return value

    @classmethod
    def get_amount_sum(cls, queryset):
        value = queryset.aggregate(amount=models.Sum('amount')).get('amount')
        return format_amount(value, trim_empty_pence=True) or '—'

    @property
    def creditable(self):
        return self.queryset.filter(**CREDITABLE_FILTERS)

    @property
    def credited(self):
        return self.queryset.filter(**CREDITED_FILTERS)

    @property
    def refundable(self):
        return self.queryset.filter(**REFUNDABLE_FILTERS)

    @property
    def refunded(self):
        return self.queryset.filter(**REFUNDED_FILTERS)

    @property
    def unidentified(self):
        return self.queryset.filter(**UNIDENTIFIED_FILTERS)

    @property
    def well_formed_references(self):
        # taken from transaction-uploader
        reference_pattern = re.compile(
            '''
            ^
            [^a-zA-Z]*                    # skip until first letter
            ([A-Za-z][0-9]{4}[A-Za-z]{2}) # match the prisoner number
            \D*                           # skip until next digit
            ([0-9]{1,2})                  # match 1 or 2 digit day of month
            \D*                           # skip until next digit
            ([0-9]{1,2})                  # match 1 or 2 digit month
            \D*                           # skip until next digit
            ([0-9]{4}|[0-9]{2})           # match 4 or 2 digit year
            \D*                           # skip until end
            $
            ''',
            re.X
        )

        candidate_credits = self.queryset.filter(
            category=TRANSACTION_CATEGORY.CREDIT,
            source__in=[
                TRANSACTION_SOURCE.BANK_TRANSFER,
                TRANSACTION_SOURCE.ONLINE,
            ],
        ).values_list('reference', flat=True)
        return reduce(lambda count, reference: count + (1 if reference_pattern.match(reference) else 0),
                      candidate_credits, 0)

    def get_table(self):
        return [
            {
                'title': _('Valid credits'),
                'value': self.get_amount_sum(self.creditable),
            },
            {
                'title': _('Credits to refund'),
                'value': self.get_amount_sum(self.refundable),
            },
            {
                'title': _('Curent balance'),
                'value': self.get_current_balance(),
            },
            {
                'title': _('Valid credits'),
                'value': self.get_count(self.creditable),
            },
            {
                'title': _('Credits to refund'),
                'value': self.get_count(self.refundable),
            },
            {
                'title': _('Well-formed references'),
                'value': self.well_formed_references,
                'help_text': _('References that were can be formatted into a prisoner number and date of birth'),
            },
            {
                'title': _('Credited'),
                'value': self.get_count(self.credited),
                'help_text': _('Credited through the Cashbook tool'),
            },
            {
                'title': _('Refunded'),
                'value': self.get_count(self.refunded),
                'help_text': _('Refunds file downloaded through the Bank Admin tool'),
            },
            {
                'title': _('Unidentified credits'),
                'value': self.get_count(self.unidentified),
                'help_text': _('Credits that do not match an offender in the system and cannot be refunded'),
            },
        ]
