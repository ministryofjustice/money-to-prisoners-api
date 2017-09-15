import datetime
import json
import types

from django import forms
from django.contrib.admin import widgets as admin_widgets
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.encoding import force_text
from django.utils.functional import cached_property
from django.utils.html import escapejs
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _

from core.dashboards import DashboardChangeForm, DashboardModule
from core.views import DashboardView
from credit.models import Credit, CREDIT_RESOLUTION, CREDIT_STATUS
from prison.models import Prison
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


class DateField(forms.DateField):
    widget = admin_widgets.AdminDateWidget

    def get_bound_field(self, form, field_name):
        bound_field = super().get_bound_field(form, field_name)
        super_css_classes = bound_field.css_classes

        def css_classes(_, extra_classes=None):
            classes = super_css_classes(extra_classes=extra_classes)
            return (classes + ' row_%s' % field_name).strip()

        bound_field.css_classes = types.MethodType(css_classes, bound_field)
        return bound_field


class SimpleDurationField(forms.FloatField):
    default_error_messages = {
        'invalid': _('Enter number of days'),
    }

    def prepare_value(self, value):
        if isinstance(value, datetime.timedelta):
            return value.days + value.seconds / 86400
        return super().prepare_value(value)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.timedelta):
            return value
        try:
            return datetime.timedelta(days=float(value))
        except ValueError:
            raise ValidationError(self.error_messages['invalid'], code='invalid')


class CreditReportForm(DashboardChangeForm):
    date_range = forms.ChoiceField(
        label=_('Date range'),
        choices=[
            ('today', _('Today')),
            ('yesterday', _('Yesterday')),
            ('this_week', _('This week')),
            ('last_week', _('Last week')),
            ('four_weeks', _('Last 4 weeks')),
            ('this_month', _('This month')),
            ('last_month', _('Last month')),
            # ('all', _('Since the beginning')),
            ('custom', _('Specify a range…')),
        ],
        initial='this_week',
        required=False,
    )
    start_date = DateField(label=_('From date'), required=False)
    end_date = DateField(label=_('To date'), required=False)
    prison = forms.ModelChoiceField(
        queryset=Prison.objects.all(),
        label=_('Prison'),
        empty_label=_('All prisons'),
        required=False,
    )
    min_crediting_time = SimpleDurationField(label=_('Min. time to credit'), required=False)

    prevent_auto_reload = True
    error_messages = {
        'date_order': _('End date must be after start date'),
        'big_range': _('Choose a smaller date range'),
    }

    def clean_end_date(self):
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        if start_date and end_date and self.cleaned_data.get('date_range') == 'custom':
            if end_date < start_date:
                raise forms.ValidationError(self.error_messages['date_order'], code='date_order')
            if end_date - start_date > datetime.timedelta(days=60):
                raise forms.ValidationError(self.error_messages['big_range'], code='big_range')
        return end_date

    @cached_property
    def today(self):
        return timezone.localtime(timezone.now()).date()

    @cached_property
    def yesterday(self):
        return self.today - datetime.timedelta(days=1)

    @cached_property
    def earliest(self):
        try:
            return timezone.localtime(Credit.objects.earliest().received_at).date()
        except Credit.DoesNotExist:
            pass

    @cached_property
    def latest(self):
        try:
            return timezone.localtime(Credit.objects.latest().received_at).date()
        except Credit.DoesNotExist:
            pass

    @cached_property
    def this_week(self):
        monday = self.today - datetime.timedelta(days=self.today.weekday())
        return monday, monday + datetime.timedelta(days=6)

    @cached_property
    def last_week(self):
        monday = self.today - datetime.timedelta(days=self.today.weekday() + 7)
        return monday, monday + datetime.timedelta(days=6)

    @cached_property
    def four_weeks(self):
        return self.today - datetime.timedelta(days=4 * 7), self.today

    @cached_property
    def this_month(self):
        return self.today.replace(day=1), self.today

    @cached_property
    def last_month(self):
        last_day = self.today.replace(day=1) - datetime.timedelta(days=1)
        return last_day.replace(day=1), last_day

    def get_date_range(self):
        date_range = self.cleaned_data['date_range'] or self['date_range'].field.initial
        if date_range == 'custom' and (self.cleaned_data.get('start_date') or self.cleaned_data.get('end_date')):
            received_at_start = self.cleaned_data.get('start_date', self.earliest)
            received_at_end = self.cleaned_data.get('end_date', self.latest)
            if received_at_start == received_at_end:
                short_title = format_date(received_at_start, 'j M Y')
            else:
                if received_at_start.replace(day=1) == received_at_end.replace(day=1):
                    from_date_format = 'j'
                elif received_at_start.replace(month=1, day=1) == received_at_end.replace(month=1, day=1):
                    from_date_format = 'j M'
                else:
                    from_date_format = 'j M Y'
                short_title = _('%(from)s to %(to)s') % {
                    'from': format_date(received_at_start, from_date_format),
                    'to': format_date(received_at_end, 'j M Y')
                }
            return {
                'range': (received_at_start, received_at_end),
                'short_title': short_title,
                'title': short_title,
            }
        elif date_range in ('this_week', 'last_week', 'four_weeks', 'this_month', 'last_month'):
            received_at_start, received_at_end = getattr(self, date_range)
            short_title = dict(self['date_range'].field.choices)[date_range]
            if date_range in ('this_month', 'last_month'):
                month = format_date(received_at_start, 'N Y')
                title = '%(title)s, %(month)s' % {
                    'title': short_title,
                    'month': month,
                }
                short_title = month
            else:
                title = '%(title)s, commencing %(day)s' % {
                    'title': short_title,
                    'day': format_date(received_at_start, 'j N'),
                }
            return {
                'range': (received_at_start, received_at_end),
                'short_title': short_title,
                'title': title,
            }
        elif date_range in ('today', 'yesterday'):
            received_at = getattr(self, date_range)
            short_title = dict(self['date_range'].field.choices)[date_range]
            return {
                'range': (received_at,),
                'short_title': short_title,
                'title': '%(title)s, %(day)s' % {
                    'title': short_title,
                    'day': format_date(received_at, 'j N'),
                },
            }

        # all time
        return {
            'range': (),
            'short_title': _('Since the beginning'),
            'title': _('Since the beginning'),
        }

    def get_prison(self):
        if self.is_valid():
            return self.cleaned_data['prison']

    def get_min_crediting_time(self):
        if self.is_valid():
            return self.cleaned_data['min_crediting_time']

    def get_report_parameters(self):
        credit_queryset = Credit.objects.all()
        transaction_queryset = Transaction.objects.all()

        prison = self.get_prison()
        if prison:
            credit_queryset = credit_queryset.filter(prison=prison)
            transaction_queryset = transaction_queryset.filter(credit__prison=prison)

        min_crediting_time = self.get_min_crediting_time()
        if min_crediting_time:
            credit_queryset = credit_queryset.filter(
                creditingtime__crediting_time__gte=min_crediting_time
            )
            transaction_queryset = transaction_queryset.filter(
                credit__creditingtime__crediting_time__gte=min_crediting_time
            )

        chart_credit_queryset = credit_queryset.filter()

        date_range = self.get_date_range()
        if len(date_range['range']) == 2:
            title = date_range['title']
            received_at_start, received_at_end = date_range['range']
            date_filters = {
                'received_at__date__gte': received_at_start,
                'received_at__date__lte': received_at_end,
            }
            admin_filter_string = 'received_at__date__gte=%s&' \
                                  'received_at__date__lte=%s' % (received_at_start.isoformat(),
                                                                 received_at_end.isoformat())
            chart_title = date_range['short_title']
            chart_start_date = received_at_start
            chart_end_date = received_at_end
        elif len(date_range['range']) == 1:
            title = date_range['title']
            received_at, = date_range['range']
            date_filters = {
                'received_at__date': received_at
            }
            admin_filter_string = 'received_at__day=%d&' \
                                  'received_at__month=%d&' \
                                  'received_at__year=%d' % (received_at.day,
                                                            received_at.month,
                                                            received_at.year)
            chart_title = _('Last 4 weeks')
            chart_start_date = self.four_weeks[0]
            chart_end_date = self.four_weeks[1]
        else:
            title = date_range['title']
            date_filters = {}
            admin_filter_string = ''
            chart_title = date_range['short_title']
            chart_start_date = None
            chart_end_date = None

        extra_titles = []
        if prison:
            extra_titles.append(_('only for %(prison)s') % {'prison': prison})
        if min_crediting_time:
            extra_titles.append(_('time to credit at least %(days)s days') % {
                'days': min_crediting_time.days + min_crediting_time.seconds / 86400
            })
        if extra_titles:
            title += ' (%s)' % ', '.join(extra_titles)

        credit_queryset = credit_queryset.filter(**date_filters)
        transaction_queryset = transaction_queryset.filter(**date_filters)
        if chart_start_date:
            chart_credit_queryset = chart_credit_queryset.filter(received_at__date__gte=chart_start_date)
        if chart_end_date:
            chart_credit_queryset = chart_credit_queryset.filter(received_at__date__lte=chart_end_date)

        return {
            'title': title,
            'credit_queryset': credit_queryset,
            'transaction_queryset': transaction_queryset,
            'admin_filter_string': admin_filter_string,
            'chart_title': chart_title,
            'chart_credit_queryset': chart_credit_queryset,
            'chart_start_date': chart_start_date,
            'chart_end_date': chart_end_date,
        }


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
        self.form = CreditReportForm(data=self.cookie_data or {})
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
        if self.dashboard_view and self.dashboard_view.request.user.has_perm('credit.change_credit'):
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
        return self.credit_queryset.exclude(resolution=CREDIT_RESOLUTION.INITIAL)

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
