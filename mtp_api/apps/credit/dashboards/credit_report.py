import datetime
import json

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escapejs
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _

from core.dashboards import DashboardModule
from core.views import DashboardView
from credit.dashboards.credit_forms import CreditForm
from credit.models import Credit, CREDIT_RESOLUTION, CREDIT_STATUS
from transaction.models import Transaction, TRANSACTION_CATEGORY, TRANSACTION_SOURCE, TRANSACTION_STATUS

# credit-specific
CREDITABLE_FILTERS = Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED] | \
                     Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDIT_PENDING]
CREDITED_FILTERS = Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED]
REFUNDABLE_FILTERS = Credit.STATUS_LOOKUP[CREDIT_STATUS.REFUNDED] | \
                     Credit.STATUS_LOOKUP[CREDIT_STATUS.REFUND_PENDING]
# NB: refundable does not consider debit card payments since refunds there have not been worked out
REFUNDED_FILTERS = Credit.STATUS_LOOKUP[CREDIT_STATUS.REFUNDED]
TRANSACTION_ERROR_FILTERS = (
    models.Q(transaction__source=TRANSACTION_SOURCE.BANK_TRANSFER,
             prison__isnull=True) |
    models.Q(transaction__source=TRANSACTION_SOURCE.BANK_TRANSFER,
             blocked=True)
)

# transaction-specific
BANK_TRANSFER_CREDIT_FILTERS = models.Q(category=TRANSACTION_CATEGORY.CREDIT, source=TRANSACTION_SOURCE.BANK_TRANSFER)
ANONYMOUS_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.ANONYMOUS]
UNIDENTIFIED_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.UNIDENTIFIED]
ANOMALOUS_FILTERS = Transaction.STATUS_LOOKUP[TRANSACTION_STATUS.ANOMALOUS]


class CreditReportChart:
    def __init__(self, title, credit_queryset, start_date, end_date):
        self.title = title
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
            self.max_sum, str(escapejs(self.title)),
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
    slug = 'credit_report'
    template = 'core/dashboard/credit-report.html'
    column_count = 3
    title = _('Credit report')
    priority = 100

    class Media:
        css = {
            'all': ('stylesheets/credit-report.css',)
        }
        js = (
            'admin/js/core.js',
            'https://www.gstatic.com/charts/loader.js',
            'javascripts/google-charts.js',
            'javascripts/credit-report.js',
        )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.view.fullscreen:
            self.enabled = False
            return
        self.form = CreditForm(data=self.cookie_data or {})
        if not self.form.is_valid():
            self.credit_queryset = Credit.objects.none()
            self.transaction_queryset = Transaction.objects.none()
            return
        report_parameters = self.form.get_report_parameters()
        self.range_title = report_parameters['title']
        self.credit_queryset = report_parameters['credit_queryset']
        self.transaction_queryset = report_parameters['transaction_queryset']
        self.chart = CreditReportChart(title=report_parameters['chart_title'],
                                       credit_queryset=report_parameters['chart_credit_queryset'],
                                       start_date=report_parameters['chart_start_date'],
                                       end_date=report_parameters['chart_end_date'])
        if self.view and self.view.request.user.has_perm('credit.change_credit'):
            self.change_list_url = '%s?%s' % (reverse('admin:credit_credit_changelist'),
                                              report_parameters['admin_filter_string'])

    # statistic formatting methods

    @classmethod
    def get_count(cls, queryset):
        return queryset.count()

    @classmethod
    def get_amount_sum(cls, queryset):
        return queryset.aggregate(amount=models.Sum('amount')).get('amount')

    @classmethod
    def get_top_prisons(cls, queryset, top=3):
        creditable_prisons = queryset.values('prison__name').annotate(count=models.Count('pk')).order_by('-count')[:top]
        for creditable_prison in creditable_prisons:
            yield {
                'prison': creditable_prison['prison__name'],
                'count': creditable_prison['count'],
            }

    # query set methods

    def get_received_queryset(self):
        # NB: includes only non-administrative bank transfers and debit card payments that are in progress or completed
        return self.credit_queryset.exclude(resolution__in=(CREDIT_RESOLUTION.INITIAL, CREDIT_RESOLUTION.FAILED))

    def get_received_transaction_queryset(self):
        return self.get_received_queryset().filter(transaction__isnull=False)

    def get_received_payment_queryset(self):
        return self.get_received_queryset().filter(payment__isnull=False)

    @property
    def received_count(self):
        return self.get_count(self.get_received_queryset())

    @property
    def received_amount(self):
        return self.get_amount_sum(self.get_received_queryset())

    @property
    def received_transaction_count(self):
        return self.get_count(self.get_received_transaction_queryset())

    @property
    def received_transaction_amount(self):
        return self.get_amount_sum(self.get_received_transaction_queryset())

    @property
    def received_payment_count(self):
        return self.get_count(self.get_received_payment_queryset())

    @property
    def received_payment_amount(self):
        return self.get_amount_sum(self.get_received_payment_queryset())

    def get_top_recevied_by_prison(self, top=4):
        return self.get_top_prisons(self.get_received_queryset(), top=top)

    def get_creditable_queryset(self):
        return self.credit_queryset.filter(CREDITABLE_FILTERS)

    def get_creditable_transaction_queryset(self):
        return self.get_creditable_queryset().filter(transaction__isnull=False)

    def get_creditable_payment_queryset(self):
        return self.get_creditable_queryset().filter(payment__isnull=False)

    @property
    def creditable_count(self):
        return self.get_count(self.get_creditable_queryset())

    @property
    def creditable_amount(self):
        return self.get_amount_sum(self.get_creditable_queryset())

    @property
    def creditable_transaction_count(self):
        return self.get_count(self.get_creditable_transaction_queryset())

    @property
    def creditable_payment_count(self):
        return self.get_count(self.get_creditable_payment_queryset())

    @property
    def creditable_payment_proportion(self):
        creditable = self.get_creditable_queryset().count()
        if creditable == 0:
            return None
        return self.get_creditable_payment_queryset().count() / creditable

    def get_top_creditable_by_prison(self, top=4):
        return self.get_top_prisons(self.get_creditable_queryset(), top=top)

    def get_credited_queryset(self):
        return self.credit_queryset.filter(CREDITED_FILTERS)

    @property
    def average_crediting_time(self):
        return self.get_credited_queryset().aggregate(avg=models.Avg('creditingtime__crediting_time',
                                                                     output_field=models.DurationField())).get('avg')

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
            BANK_TRANSFER_CREDIT_FILTERS,
            credit__prisoner_dob__isnull=False,
            credit__prisoner_number__isnull=False,
        )

    @property
    def valid_reference_count(self):
        return self.get_count(self.get_valid_reference_queryset())

    def get_references_with_slash_queryset(self):
        regex = r'^[A-Z]\d{4}[A-Z]{2}/\d{2}/\d{2}/\d{4}$'
        return self.transaction_queryset.filter(
            BANK_TRANSFER_CREDIT_FILTERS,
            models.Q(reference__regex=regex) | models.Q(sender_name__regex=regex)
        )

    @property
    def references_with_slash_count(self):
        return self.get_count(self.get_references_with_slash_queryset())

    def get_unmatched_reference_queryset(self):
        return self.transaction_queryset.filter(
            BANK_TRANSFER_CREDIT_FILTERS,
            credit__prison__isnull=True,
            credit__prisoner_dob__isnull=False,
            credit__prisoner_number__isnull=False,
        )

    @property
    def unmatched_reference_count(self):
        return self.get_count(self.get_unmatched_reference_queryset())

    def get_invalid_reference_queryset(self):
        return self.transaction_queryset.filter(
            BANK_TRANSFER_CREDIT_FILTERS,
            credit__prisoner_dob__isnull=True,
            credit__prisoner_number__isnull=True,
        )

    @property
    def invalid_reference_count(self):
        return self.get_count(self.get_invalid_reference_queryset())

    def get_transaction_error_queryset(self):
        return self.credit_queryset.filter(TRANSACTION_ERROR_FILTERS)

    @property
    def transaction_error_rate(self):
        received = self.received_transaction_count
        if received == 0:
            return None
        return self.get_transaction_error_queryset().count() / received
