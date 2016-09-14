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

from core.dashboards import DashboardModule
from core.views import DashboardView
from credit.constants import CREDIT_RESOLUTION, CREDIT_STATUS
from credit.models import Credit
from payment.constants import PAYMENT_STATUS
from transaction.constants import TRANSACTION_SOURCE, TRANSACTION_STATUS
from transaction.models import Transaction
from transaction.utils import format_amount, format_number, format_percentage

# credit-specific
CREDITABLE_FILTERS = models.Q(prison__isnull=False) & \
                     (models.Q(transaction__incomplete_sender_info=False) |
                      models.Q(resolution=CREDIT_RESOLUTION.CREDITED))
CREDITED_FILTERS = Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED]
REFUNDABLE_FILTERS = models.Q(prison__isnull=True, transaction__incomplete_sender_info=False)
# NB: refundable does not consider debit card payments since refunds there have not been worked out
REFUNDED_FILTERS = Credit.STATUS_LOOKUP[CREDIT_STATUS.REFUNDED]
ERROR_FILTERS = (models.Q(transaction__source=TRANSACTION_SOURCE.BANK_TRANSFER, prison__isnull=True) |
                 models.Q(payment__isnull=False) & ~models.Q(payment__status=PAYMENT_STATUS.TAKEN))

# transaction-specific
ANONYMOUS_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.ANONYMOUS]
UNIDENTIFIED_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.UNIDENTIFIED]
ANOMALOUS_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.ANOMALOUS]


class CreditReportDateForm(forms.Form):
    date_range = forms.ChoiceField(
        label=_('Date range'),
        choices=(
            ('latest', _('Latest day')),
            ('four_weeks', _('Last 4 weeks')),
            ('this_month', _('This month')),
            ('last_month', _('Last month')),
            ('all', _('Since the beginning')),
        ),
        initial='latest',
    )


class CreditReportChart:
    def __init__(self, title, start_date=None, end_date=None):
        self.title = title
        credit_queryset = Credit.objects.all()
        if start_date:
            credit_queryset = credit_queryset.filter(received_at__date__gte=start_date)
        if end_date:
            credit_queryset = credit_queryset.filter(received_at__date__lte=end_date)
        self.start_date = start_date or \
            timezone.localtime(credit_queryset.earliest().received_at).date()
        self.end_date = end_date or \
            timezone.localtime(credit_queryset.latest().received_at).date()
        self.credit_queryset = credit_queryset
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
            credit_queryset = self.credit_queryset.filter(received_at__date=date)
            creditable = credit_queryset.filter(CREDITABLE_FILTERS).count() or 0
            refundable = credit_queryset.filter(REFUNDABLE_FILTERS).count() or 0
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
class CreditReport(DashboardModule):
    template = 'core/dashboard/credit-report.html'
    column_count = 3
    title = _('Credit report')
    show_stand_out = True
    priority = 100
    cookie_key = 'credit-report'

    class Media:
        css = {
            'all': ('core/css/credit-report.css',)
        }
        js = (
            'https://www.gstatic.com/charts/loader.js',
            'core/js/google-charts.js',
            'core/js/credit-report.js',
        )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        today = timezone.localtime(timezone.now()).date()

        def get_four_weeks():
            return today - datetime.timedelta(days=4 * 7), today

        def get_this_month():
            return today.replace(day=1), today

        def get_last_month():
            last_day = today.replace(day=1) - datetime.timedelta(days=1)
            return last_day.replace(day=1), last_day

        self.form = CreditReportDateForm(data=self.cookie_data)
        date_range = self.form['date_range'].value()
        credit_queryset = Credit.objects.all()
        transaction_queryset = Transaction.objects.all()
        queryset_filters = {}
        if date_range == 'all':
            self.range_title = _('All credits')
            received_at_start, received_at_end = None, None
            filter_string = ''
            chart_title = self.range_title
        elif date_range in ('four_weeks', 'this_month', 'last_month'):
            if date_range == 'four_weeks':
                received_at_start, received_at_end = get_four_weeks()
                chart_title = _('Last 4 weeks')
                self.range_title = chart_title
            else:
                if date_range == 'last_month':
                    received_at_start, received_at_end = get_last_month()
                else:
                    received_at_start, received_at_end = get_this_month()
                chart_title = format_date(received_at_start, 'N Y')
                self.range_title = _('Credits received in %(month)s') % {
                    'month': chart_title
                }

            queryset_filters = {
                'received_at__date__gte': received_at_start,
                'received_at__date__lte': received_at_end,
            }
            filter_string = 'received_at__date__gte=%s&' \
                            'received_at__date__lte=%s' % (received_at_start.isoformat(),
                                                           received_at_end.isoformat())
        else:
            try:
                received_at = timezone.localtime(Credit.objects.latest().received_at).date()
            except Credit.DoesNotExist:
                received_at = (timezone.localtime(timezone.now()) - datetime.timedelta(days=1)).date()
            self.range_title = _('Latest credits received on %(date)s') % {
                'date':  format_date(received_at, 'j N')
            }
            queryset_filters = {
                'received_at__date': received_at
            }
            filter_string = 'received_at__day=%d&' \
                            'received_at__month=%d&' \
                            'received_at__year=%d' % (received_at.day,
                                                      received_at.month,
                                                      received_at.year)

            # display chart of last 4 weeks
            received_at_start, received_at_end = get_four_weeks()
            chart_title = _('Last 4 weeks')

        self.credit_queryset = credit_queryset.filter(**queryset_filters)
        self.transaction_queryset = transaction_queryset.filter(**queryset_filters)
        self.chart = CreditReportChart(
            chart_title,
            start_date=received_at_start,
            end_date=received_at_end,
        )
        if self.dashboard_view and self.dashboard_view.request.user.has_perm('credit.change_credit'):
            self.change_list_url = reverse('admin:credit_credit_changelist') + '?' + filter_string

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

    def get_received_queryset(self):
        # NB: includes only non-administrative bank transfers and debit card payments that are in progress or completed
        return self.credit_queryset.exclude(resolution=CREDIT_RESOLUTION.INITIAL)

    @property
    def received_count(self):
        return self.get_count(self.get_received_queryset())

    @property
    def received_amount(self):
        return self.get_amount_sum(self.get_received_queryset())

    def get_creditable_queryset(self):
        return self.credit_queryset.filter(CREDITABLE_FILTERS)

    @property
    def creditable_count(self):
        return self.get_count(self.get_creditable_queryset())

    @property
    def creditable_amount(self):
        return self.get_amount_sum(self.get_creditable_queryset())

    def get_credited_queryset(self):
        return self.credit_queryset.filter(CREDITED_FILTERS)

    @property
    def credited_count(self):
        return self.get_count(self.get_credited_queryset())

    def get_refundable_queryset(self):
        return self.credit_queryset.filter(REFUNDABLE_FILTERS)

    @property
    def refundable_count(self):
        return self.get_count(self.get_refundable_queryset())

    @property
    def refundable_amount(self):
        return self.get_amount_sum(self.get_refundable_queryset())

    def get_refunded_queryset(self):
        return self.credit_queryset.filter(REFUNDED_FILTERS)

    @property
    def refunded_count(self):
        return self.get_count(self.get_refunded_queryset())

    def get_anonymous_queryset(self):
        return self.transaction_queryset.filter(ANONYMOUS_FILTERS)

    @property
    def anonymous_count(self):
        return self.get_count(self.get_anonymous_queryset())

    def get_unidentified_queryset(self):
        return self.transaction_queryset.filter(UNIDENTIFIED_FILTERS)

    @property
    def unidentified_count(self):
        return self.get_count(self.get_unidentified_queryset())

    def get_anomalous_queryset(self):
        return self.transaction_queryset.filter(ANOMALOUS_FILTERS)

    @property
    def anomalous_count(self):
        return self.get_count(self.get_anomalous_queryset())

    def get_valid_reference_queryset(self):
        return self.transaction_queryset.filter(
            credit__prisoner_dob__isnull=False,
            credit__prisoner_number__isnull=False,
        )

    @property
    def valid_reference_count(self):
        return self.get_count(self.get_valid_reference_queryset())

    def get_unmatched_reference_queryset(self):
        return self.transaction_queryset.filter(
            credit__prison__isnull=True,
            credit__prisoner_dob__isnull=False,
            credit__prisoner_number__isnull=False,
        )

    @property
    def unmatched_reference_count(self):
        return self.get_count(self.get_unmatched_reference_queryset())

    def get_invalid_reference_queryset(self):
        return self.transaction_queryset.filter(
            credit__prisoner_dob__isnull=True,
            credit__prisoner_number__isnull=True,
        )

    @property
    def invalid_reference_count(self):
        return self.get_count(self.get_invalid_reference_queryset())

    def get_error_queryset(self):
        return self.credit_queryset.filter(ERROR_FILTERS)

    @property
    def error_rate(self):
        received = self.get_received_queryset().count()
        if received == 0:
            return '–'
        return format_percentage(self.get_error_queryset().count() / received)
