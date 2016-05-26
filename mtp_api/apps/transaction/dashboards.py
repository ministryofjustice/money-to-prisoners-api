import datetime
import json

from django import forms
from django.core.urlresolvers import reverse
from django.db import models
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.encoding import force_text
from django.utils.html import escapejs
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _

from account.models import Balance
from credit.constants import CREDIT_RESOLUTION
from core.dashboards import DashboardModule
from core.views import DashboardView
from transaction.constants import TRANSACTION_STATUS
from transaction.models import Transaction
from transaction.utils import format_amount, format_number

CREDITABLE_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.CREDITABLE]
CREDITED_FILTERS = (
    models.Q(credit__resolution=CREDIT_RESOLUTION.CREDITED)
)
REFUNDABLE_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.REFUNDABLE]
REFUNDED_FILTERS = (
    models.Q(credit__resolution=CREDIT_RESOLUTION.REFUNDED)
)
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
    def __init__(self, queryset, title, start_date=None, end_date=None):
        self.queryset = queryset
        self.title = title
        self.start_date = start_date or \
            timezone.localtime(self.queryset.earliest().received_at).date()
        self.end_date = end_date or \
            timezone.localtime(self.queryset.latest().received_at).date()
        self.max_sum = 0
        self.max_creditable = 0
        self.max_creditable_date = None
        self.max_refundable = 0
        self.max_refundable_date = None
        self.weekends = []

    @property
    def data(self):
        rows = '[%s]' % ','.join(
            '[new Date(%d,%d,%d),%d,%s,%d,%s]' % (
                date.year, date.month - 1, date.day,
                creditable, json.dumps(self.creditable_annotation(date)),
                refundable, json.dumps(self.refundable_annotation(date)),
            )
            for date, creditable, refundable in self.rows
        )
        if len(self.weekends) > 8:
            self.weekends = []
        weekends = '[%s]' % ','.join(
            'new Date(%d,%d,%d)' % (date.year, date.month - 1, date.day)
            for date in self.weekends
        )
        return mark_safe('{columns: %s, rows: %s, weekends: %s, max: %d, title: "%s"}' % (
            json.dumps(self.columns), rows, weekends,
            self.max_sum, force_text(escapejs(self.title)),
        ))

    @property
    def columns(self):
        return [
            {'type': 'date', 'label': gettext('Date'), 'role': 'domain'},
            {'type': 'number', 'label': gettext('Valid credits'), 'role': 'data'},
            {'type': 'string', 'role': 'annotation'},
            {'type': 'number', 'label': gettext('Credits to refund'), 'role': 'data'},
            {'type': 'string', 'role': 'annotation'},
        ]

    @property
    def rows(self):
        days = (self.end_date - self.start_date).days
        if days > 100:
            date_stride = days // 100
        else:
            date_stride = 1
        date_stride = datetime.timedelta(days=date_stride)

        data = []
        date = self.start_date
        while date <= self.end_date:
            if date.weekday() > 4:
                self.weekends.append(date)
            transactions = self.queryset.filter(received_at__date=date)
            creditable = transactions.filter(CREDITABLE_FILTERS).count() or 0
            refundable = transactions.filter(REFUNDABLE_FILTERS).count() or 0
            data.append([date, creditable, refundable])
            max_sum = creditable + refundable
            if max_sum >= self.max_sum:
                self.max_sum = max_sum
            if creditable >= self.max_creditable:
                self.max_creditable = creditable
                self.max_creditable_date = date
            if refundable >= self.max_refundable:
                self.max_refundable = refundable
                self.max_refundable_date = date
            date += date_stride
        return data

    def creditable_annotation(self, date):
        if date == self.max_creditable_date:
            return str(self.max_creditable)

    def refundable_annotation(self, date):
        if date == self.max_refundable_date:
            return str(self.max_refundable)


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
            'core/js/google-charts.js',
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
            self.chart = TransactionReportChart(self.queryset, self.title)
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
                format_date(received_at_start, 'N'),
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

        if self.dashboard_view and self.dashboard_view.request.user.has_perm('credit.change_credit'):
            self.change_list_url = reverse('admin:credit_credit_changelist') + '?' + filter_string

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
        return self.queryset.filter(CREDITABLE_FILTERS)

    @property
    def credited(self):
        return self.queryset.filter(CREDITED_FILTERS)

    @property
    def refundable(self):
        return self.queryset.filter(REFUNDABLE_FILTERS)

    @property
    def refunded(self):
        return self.queryset.filter(REFUNDED_FILTERS)

    @property
    def unidentified(self):
        return self.queryset.filter(UNIDENTIFIED_FILTERS)

    @property
    def well_formed_references(self):
        return self.queryset.filter(
            credit__prisoner_dob__isnull=False,
            credit__prisoner_number__isnull=False,
        ).count()

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
