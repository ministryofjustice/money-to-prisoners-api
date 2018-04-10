import datetime

from django.db import models
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy as _, ngettext

from core.dashboards import DashboardModule
from core.views import DashboardView
from credit.models import Credit, CREDIT_STATUS
from disbursement.models import Disbursement, DISBURSEMENT_RESOLUTION
from performance.forms import SavingsDashboardForm
from performance.models import DigitalTakeup, PredictedPostalCredits
from transaction.utils import format_amount, format_number, format_percentage

CREDITABLE_FILTERS = Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED] | \
                     Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDIT_PENDING]


def valid_credit_stats(since, until=None):
    queryset = Credit.objects.filter(CREDITABLE_FILTERS)
    if until:
        queryset = queryset.filter(received_at__range=(since, until))
    else:
        queryset = queryset.filter(received_at__gte=since)
    stat = queryset.aggregate(count=models.Count('*'), amount=models.Sum('amount'))
    stat['amount'] = stat['amount'] or 0
    stat['number'] = format_number(stat['count'], truncate_after=1000000)
    return {
        'title': ngettext('%(number)s credit received', '%(number)s credits received', stat['count']) % stat,
        'value': format_amount(stat['amount'], trim_empty_pence=True, truncate_after=1000000),
    }


def pending_credits_stats(since, until=None):
    queryset = Credit.objects.credit_pending()
    if until:
        queryset = queryset.filter(received_at__range=(since, until))
    else:
        queryset = queryset.filter(received_at__gte=since)
    count = queryset.aggregate(count=models.Count('*'))['count']
    return {
        'title': ngettext('Credit pending', 'Credits pending', count),
        'value': format_number(count, truncate_after=1000000),
    }


def digital_takeup_stats(since, until=None):
    if until:
        queryset = DigitalTakeup.objects.filter(date__range=(since, until))
    else:
        queryset = DigitalTakeup.objects.filter(date__gte=since)
    digital_takeup = queryset.mean_digital_takeup()
    if digital_takeup is None:
        digital_takeup = '?'
    else:
        digital_takeup = format_percentage(digital_takeup)
    return {
        'title': _('Digital take-up for credits'),
        'value': digital_takeup,
    }


def valid_disbursement_stats(since, until=None):
    queryset = Disbursement.objects.exclude(resolution=DISBURSEMENT_RESOLUTION.REJECTED)
    if until:
        queryset = queryset.filter(created__range=(since, until))
    else:
        queryset = queryset.filter(created__gte=since)
    stat = queryset.aggregate(count=models.Count('*'), amount=models.Sum('amount'))
    stat['amount'] = stat['amount'] or 0
    stat['number'] = format_number(stat['count'], truncate_after=1000000)
    return {
        'title': ngettext('%(number)s disbursement created', '%(number)s disbursements created', stat['count']) % stat,
        'value': format_amount(stat['amount'], trim_empty_pence=True, truncate_after=1000000),
    }


def pending_disbursements_stats(since, until=None):
    queryset = Disbursement.objects \
        .exclude(resolution=DISBURSEMENT_RESOLUTION.REJECTED) \
        .exclude(resolution=DISBURSEMENT_RESOLUTION.SENT)
    if until:
        queryset = queryset.filter(created__range=(since, until))
    else:
        queryset = queryset.filter(created__gte=since)
    count = queryset.aggregate(count=models.Count('*'))['count']
    return {
        'title': ngettext('Disbursement pending', 'Disbursements pending', count),
        'value': format_number(count, truncate_after=1000000),
    }


@DashboardView.register_dashboard
class PerformanceOverview(DashboardModule):
    slug = 'performance_overview'
    template = 'core/dashboard/performance-overview.html'
    title = _('Prisoner money overview')
    priority = 200

    class Media:
        css = {
            'all': ('stylesheets/performance-overview.css',)
        }
        js = (
            'admin/js/core.js',
            'https://www.gstatic.com/charts/loader.js',
            'javascripts/google-charts.js',
            'javascripts/performance-overview.js',
        )

    def __init__(self, view):
        super().__init__(view)
        if not self.view.fullscreen:
            self.simple_stats = get_simple_stats()
        else:
            self.stats_pages = get_stats_pages()
            self.chart_data = get_credit_chart_data()

    @property
    def column_count(self):
        return 1 if self.view.fullscreen else 2


def get_simple_stats():
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    credited_stats = Credit.objects.credited() \
        .aggregate(count=models.Count('*'), amount=models.Sum('amount'))
    credited_stats['amount'] = credited_stats['amount'] or 0

    pending_credits = Credit.objects.credit_pending() \
        .filter(received_at__lt=today) \
        .count()

    digital_takeup = DigitalTakeup.objects.mean_digital_takeup()

    credit_stats = [
        {
            'title': _('Credited'),
            'value': format_html(
                '{}<br>{}',
                ngettext('%(number)s credit', '%(number)s credits', credited_stats['count']) % {
                    'number': format_number(credited_stats['count'], truncate_after=1000000)
                },
                format_amount(credited_stats['amount'], trim_empty_pence=True),
            ),
        },
        {
            'title': _('Pending'),
            'value': ngettext('%(number)s credit', '%(number)s credits', pending_credits) % {
                'number': format_number(pending_credits, truncate_after=1000000)
            },
        },
        {
            'title': _('Digital take-up'),
            'value': '?' if digital_takeup is None else format_percentage(digital_takeup),
        },
    ]

    sent_stats = Disbursement.objects.sent() \
        .aggregate(count=models.Count('*'), amount=models.Sum('amount'))
    sent_stats['amount'] = sent_stats['amount'] or 0

    pending_disbursements = Disbursement.objects \
        .exclude(resolution=DISBURSEMENT_RESOLUTION.REJECTED) \
        .exclude(resolution=DISBURSEMENT_RESOLUTION.SENT) \
        .count()

    disbursement_stats = [
        {
            'title': _('Sent'),
            'value': format_html(
                '{}<br>{}',
                ngettext('%(number)s disbursement', '%(number)s disbursements', sent_stats['count']) % {
                    'number': format_number(sent_stats['count'], truncate_after=1000000)
                },
                format_amount(sent_stats['amount'], trim_empty_pence=True),
            ),
        },
        {
            'title': _('Pending'),
            'value': ngettext('%(number)s disbursement', '%(number)s disbursements', pending_disbursements) % {
                'number': format_number(pending_disbursements, truncate_after=1000000)
            },
        },
    ]

    try:
        earliest_credit = Credit.objects.earliest()
    except Credit.DoesNotExist:
        earliest_credit = None
    try:
        earliest_disbursement = Disbursement.objects.earliest()
    except Disbursement.DoesNotExist:
        earliest_disbursement = None
    return {
        'credits': credit_stats,
        'earliest_credit': earliest_credit,
        'disbursements': disbursement_stats,
        'earliest_disbursement': earliest_disbursement,
    }


def get_stats_pages():
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    monday = today - datetime.timedelta(days=today.weekday())
    this_month = today.replace(day=1)
    if this_month.month == 1:
        last_month = this_month.replace(year=this_month.year - 1, month=12)
    else:
        last_month = this_month.replace(month=this_month.month - 1)
    new_year = this_month.replace(month=1)
    return [
        {
            'title': _('This week'),
            'stats': [
                valid_credit_stats(monday),
                # pending_credits_stats(monday),
                digital_takeup_stats(monday.date()),
                valid_disbursement_stats(monday),
                # pending_disbursements_stats(monday),
            ],
        },
        {
            'title': _('This month'),
            'stats': [
                valid_credit_stats(this_month),
                # pending_credits_stats(this_month),
                digital_takeup_stats(this_month.date()),
                valid_disbursement_stats(this_month),
                # pending_disbursements_stats(this_month),
            ],
        },
        {
            'title': last_month.strftime('%B'),
            'stats': [
                valid_credit_stats(last_month, this_month),
                # pending_credits_stats(last_month, this_month),
                digital_takeup_stats(last_month.date(), this_month.date() - datetime.timedelta(days=1)),
                valid_disbursement_stats(last_month, this_month),
                # pending_disbursements_stats(last_month, this_month),
            ],
        },
        {
            'title': _('This year'),
            'stats': [
                valid_credit_stats(new_year),
                # pending_credits_stats(new_year),
                digital_takeup_stats(new_year.date()),
                valid_disbursement_stats(new_year),
                # pending_disbursements_stats(new_year),
            ],
        },
    ]


def format_js(value):
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return mark_safe('"' + value + '"')
    if isinstance(value, datetime.date):
        return mark_safe('new Date("%s")' % value.isoformat())
    return mark_safe('null')


def get_credit_chart_data():
    week_count = 12
    now = timezone.now()
    monday_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=now.weekday())
    one_day = datetime.timedelta(days=1)
    one_week = datetime.timedelta(days=7)

    credit_queryset = Credit.objects.filter(CREDITABLE_FILTERS)
    column_labels = [
        {'type': 'date', 'label': gettext('Week commencing')},
        {'type': 'number', 'label': gettext('Bank transfer')},
        {'type': 'number', 'label': gettext('Debit card')},
        {'type': 'number', 'label': gettext('Post')},
    ]
    rows = []
    max_value = 0

    since, until = monday_midnight, now
    for i in range(week_count):
        aggregates = credit_queryset.filter(received_at__range=(since, until)) \
            .aggregate(transactions=models.Count('transaction'), payments=models.Count('payment'))
        transaction_count = aggregates.get('transactions') or 0
        payment_count = aggregates.get('payments') or 0
        postal_count = DigitalTakeup.objects.filter(date__range=(since.date(), until.date() - one_day)) \
            .aggregate(postal_count=models.Sum('credits_by_post')).get('postal_count') or 0
        rows.append(list(map(format_js, (
            since.date(),
            transaction_count,
            payment_count,
            postal_count,
        ))))
        max_value = max(max_value, payment_count, transaction_count, postal_count)
        since, until = since - one_week, since

    return {
        'max_value': max_value * 22 / 20,
        'chart_weeks': week_count,
        'column_labels': column_labels,
        'rows': rows,
    }


@DashboardView.register_dashboard
class SavingsDashboard(DashboardModule):
    slug = 'savings'
    template = 'core/dashboard/savings.html'
    title = _('Savings enabled')
    priority = 100
    column_count = 2

    def __init__(self, view):
        super().__init__(view)
        full_date_range = DigitalTakeup.objects.aggregate(earliest=models.Min('date'), latest=models.Max('date'))
        if not full_date_range['earliest']:
            self.enabled = False
            return
        self.form = SavingsDashboardForm(full_date_range, data=self.cookie_data.dict() if self.cookie_data else {})

    def calculate_savings(self):
        earliest, latest = self.form.cleaned_data['date_range']
        predictions = PredictedPostalCredits(from_date=earliest, to_date=latest).all()
        predictions['savings'] = (
            (self.form.cleaned_data['transaction_cost_post'] - self.form.cleaned_data['transaction_cost_mtp']) *
            predictions['credits_by_mtp']
        )
        return predictions
