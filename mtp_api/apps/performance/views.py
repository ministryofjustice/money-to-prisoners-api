import collections
from datetime import date, timedelta
import math

from django.contrib import messages
from django.contrib.admin.models import LogEntry, ADDITION as ADDITION_LOG_ENTRY
from django.db import models
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from core.forms import DigitalTakeupReportForm, PrisonPerformaceForm
from core.views import AdminViewMixin
from disbursement.models import Disbursement, DISBURSEMENT_RESOLUTION
from performance.forms import DigitalTakeupUploadForm
from performance.models import DigitalTakeup
from prison.models import Prison


class DigitalTakeupUploadView(AdminViewMixin, FormView):
    """
    Django admin view for uploading money-by-post statistics
    """
    title = _('Upload spreadsheet')
    form_class = DigitalTakeupUploadForm
    template_name = 'admin/performance/digitaltakeup/upload.html'
    success_url = reverse_lazy('admin:performance_digitaltakeup_changelist')
    required_permissions = ['performance.add_digitaltakeup', 'performance.change_digitaltakeup']
    save_message = _('Digital take-up saved for %(prison_count)d prisons')

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['opts'] = DigitalTakeup._meta
        return context_data

    def form_valid(self, form):
        self.check_takeup(form.date, form.credits_by_prison)
        form.save()
        LogEntry.objects.log_action(
            user_id=self.request.user.pk,
            content_type_id=None, object_id=None,
            object_repr=self.save_message % {
                'date': date_format(form.date, 'DATE_FORMAT'),
                'prison_count': len(form.credits_by_prison),
            },
            action_flag=ADDITION_LOG_ENTRY,
        )
        messages.success(self.request, self.save_message % {
            'date': date_format(form.date, 'DATE_FORMAT'),
            'prison_count': len(form.credits_by_prison),
        })
        return super().form_valid(form)

    def check_takeup(self, date, credits_in_spreadsheet):
        from credit.models import Log, LOG_ACTIONS

        credited = Log.objects.filter(created__date=date, action=LOG_ACTIONS.CREDITED) \
            .values('credit__prison__nomis_id') \
            .order_by('credit__prison__nomis_id') \
            .annotate(count=models.Count('credit__prison__nomis_id'))
        credited = {
            count['credit__prison__nomis_id']: count['count']
            for count in credited
        }

        credited_set = set(credited.keys())
        spreadsheet_set = set(credits_in_spreadsheet.keys())
        missing_prison_credits = sorted(credited_set - spreadsheet_set)
        extra_prison_credits = sorted(spreadsheet_set - credited_set)
        common_prison_credits = sorted(spreadsheet_set.intersection(credited_set))
        common_prison_credit_differences = [
            '%s (recevied %d, spreadsheet %d)' % (
                prison, credited[prison], credits_in_spreadsheet[prison]['credits_by_mtp']
            )
            for prison in sorted(common_prison_credits)
            if credits_in_spreadsheet[prison]['credits_by_mtp'] != credited[prison]
        ]
        if missing_prison_credits:
            messages.warning(self.request,
                             _('We received credits at these prisons, but spreadsheet is missing them:') +
                             '\n' + ', '.join(missing_prison_credits))
        if extra_prison_credits:
            messages.warning(self.request,
                             _('We did not receive credits at these prisons, but spreadsheet has them:') +
                             '\n' + ', '.join(extra_prison_credits))
        if common_prison_credit_differences:
            messages.warning(self.request,
                             _('Credits received do not match those in the spreadsheet:') +
                             '\n' + ', '.join(common_prison_credit_differences))


class PrisonPerformanceView(AdminViewMixin, TemplateView):
    title = _('Prison performance')
    template_name = 'admin/performance/prison_performance.html'
    ordering_fields = (
        'nomis_id', 'credit_post_count', 'credit_mtp_count', 'credit_uptake',
        'disbursement_count'
    )
    required_permissions = ['transaction.view_dashboard']
    excluded_nomis_ids = {'ZCH'}

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = PrisonPerformaceForm(data=self.request.GET.dict())
        if not form.is_valid():
            form = PrisonPerformaceForm(data={})
            assert form.is_valid(), 'Empty form should be valid'

        since_date = date.today() - timedelta(days=int(form.cleaned_data['days']))

        prisons = Prison.objects.exclude(
            nomis_id__in=self.excluded_nomis_ids
        ).values_list('nomis_id', 'name')

        prisons = {
            nomis_id: {
                'name': prison,
                'nomis_id': nomis_id,
                'disbursement_count': 0,
                'credit_post_count': None,
                'credit_mtp_count': None,
                'credit_uptake': None,
            }
            for nomis_id, prison in prisons
        }

        disbursements = Disbursement.objects.exclude(
            prison__in=self.excluded_nomis_ids,
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT, created__date__gte=since_date,
        ).values('prison').order_by('prison').annotate(count=models.Count('*'))
        for row in disbursements:
            prisons[row['prison']]['disbursement_count'] = row['count']

        takeup = DigitalTakeup.objects.exclude(
            prison__in=self.excluded_nomis_ids,
        ).filter(
            date__gte=since_date
        ).values('prison').order_by('prison').annotate(
            credit_post_count=models.Sum('credits_by_post'),
            credit_mtp_count=models.Sum('credits_by_mtp')
        )

        for row in takeup:
            credit_post_count, credit_mtp_count = row['credit_post_count'], row['credit_mtp_count']
            if credit_post_count or credit_mtp_count:
                credit_uptake = credit_mtp_count / (credit_post_count + credit_mtp_count)
            else:
                credit_uptake = None
            prisons[row['prison']].update(
                credit_post_count=credit_post_count,
                credit_mtp_count=credit_mtp_count,
                credit_uptake=credit_uptake,
            )

        prisons = prisons.values()
        prisons = sorted(
            prisons, key=lambda p: p[form.cleaned_data['order_by']] or 0,
            reverse=bool(form.cleaned_data['desc'])
        )

        days_query = '&'.join(
            '%s=%s' % (name, value)
            for name, value in form.cleaned_data.items()
            if name not in {'order_by', 'desc'}
        )
        context_data['form'] = form
        context_data['days_query'] = days_query
        context_data['prisons'] = prisons
        return context_data


class DigitalTakeupReport(AdminViewMixin, TemplateView):
    """
    gross savings = cost if all transactions were post - actual cost
                  = digital transactions * cost difference
    """
    title = _('Digital take-up & savings report')
    template_name = 'performance/digital-takeup-report.html'
    required_permissions = ['transaction.view_dashboard']

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = DigitalTakeupReportForm(data=self.request.GET.dict())
        if not form.is_valid():
            form = DigitalTakeupReportForm(data={})
            assert form.is_valid(), 'Empty form should be valid'

        cost_difference = form.cleaned_data['postal_cost'] - form.cleaned_data['digital_cost']
        first_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if form.cleaned_data['period'] == 'quarterly':
            rows = self.get_quarterly_rows()
            current_period = first_of_month.replace(month=math.ceil(first_of_month.month / 3) * 3 - 2)

            def format_date(d):
                return 'Q%d %d' % (math.ceil(d.month / 3), d.year)
        elif form.cleaned_data['period'] == 'financial':
            rows = self.get_financial_year_rows()
            if first_of_month.month < 4:
                current_period = first_of_month.replace(year=first_of_month.year - 1, month=4)
            else:
                current_period = first_of_month.replace(month=4)

            def format_date(d):
                if d.month < 4:
                    year = d.year - 1
                else:
                    year = d.year
                return '%(april)s %(year1)d to %(april)s %(year2)d' % {
                    'april': _('April'),
                    'year1': year,
                    'year2': year + 1,
                }
        else:
            rows = self.get_monthly_rows()
            current_period = first_of_month

            def format_date(d):
                return d.strftime('%b %Y')

        context_data['opts'] = DigitalTakeup._meta
        context_data['form'] = form
        context_data['show_reported'] = form.cleaned_data['show_reported'] == 'show'
        context_data['rows'] = list(self.process_rows(rows, current_period, format_date, cost_difference))
        return context_data

    def get_monthly_rows(self):
        yield from DigitalTakeup.objects.digital_takeup_per_month()

    def get_quarterly_rows(self):
        quarter_end_months = {3, 6, 9, 12}
        collected = collections.defaultdict(int)
        for row in self.get_monthly_rows():
            row_date = row.pop('date')
            if 'date' not in collected:
                collected['date'] = row_date
            for key, value in row.items():
                collected[key] += value
            if row_date.month in quarter_end_months:
                yield collected
                collected = collections.defaultdict(int)
        if 'date' in collected:
            yield collected

    def get_financial_year_rows(self):
        collected = collections.defaultdict(int)
        for row in self.get_monthly_rows():
            row_date = row.pop('date')
            if 'date' not in collected:
                collected['date'] = row_date
            for key, value in row.items():
                collected[key] += value
            if row_date.month == 3:
                yield collected
                collected = collections.defaultdict(int)
        if 'date' in collected:
            yield collected

    def process_rows(self, rows, current_period, format_date, cost_difference):
        for row in rows:
            if row['date'] >= current_period:
                break
            row['date'] = format_date(row['date'])
            total_reported = row['reported_credits_by_post'] + row['reported_credits_by_mtp']
            if total_reported:
                row['digital_takeup'] = row['reported_credits_by_mtp'] / total_reported
                row['extrapolated_credits_by_post'] = round(
                    (1 - row['digital_takeup']) * row['accurate_credits_by_mtp'] / row['digital_takeup']
                )
                row['savings'] = row['accurate_credits_by_mtp'] * cost_difference
            else:
                row['digital_takeup'] = None
                row['extrapolated_credits_by_post'] = None
                row['savings'] = None
            yield row
