from django import forms
from django.db import models
from django.db.models.functions import TruncMonth
from django.utils.translation import gettext_lazy as _

from core.forms import BasePeriodAdminReportForm, BasePrisonAdminReportForm
from core.views import BaseAdminReportView
from credit.models import Credit, CREDIT_RESOLUTION
from prison.models import Prison


class CreditReportForm(BasePeriodAdminReportForm):
    private_estate = forms.ChoiceField(label=_('Private estate'), choices=(
        ('include', _('Include')),
        ('exclude', _('Exclude')),
    ), initial='include')


class CreditReportAdminView(BaseAdminReportView):
    title = _('Credit report')
    template_name = 'admin/credit/credit/report.html'
    form_class = CreditReportForm

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = context_data['form']

        exclude_private_estate = form.cleaned_data['private_estate'] == 'exclude'

        current_period = form.current_period
        format_date = form.period_formatter

        rows = form.group_months_into_periods(self.get_monthly_rows(exclude_private_estate))
        rows = list(filter(lambda r: r['date'] < current_period, rows))
        for row in rows:
            row['date_label'] = format_date(row['date'])
        context_data['rows'] = rows

        context_data['opts'] = Credit._meta
        context_data['form'] = form
        context_data['exclude_private_estate'] = exclude_private_estate
        return context_data

    def get_monthly_rows(self, exclude_private_estate=False):
        queryset = Credit.objects \
            .filter(resolution=CREDIT_RESOLUTION.CREDITED) \
            .exclude(prison__in=self.excluded_nomis_ids) \
            .order_by()
        if exclude_private_estate:
            queryset = queryset.filter(prison__private_estate=False)
        return queryset \
            .annotate(date=TruncMonth('received_at')) \
            .values('date') \
            .annotate(count=models.Count('pk'), amount=models.Sum('amount')) \
            .values('date', 'count', 'amount') \
            .order_by('date')


class PrisonCreditReportForm(BasePrisonAdminReportForm):
    ordering = forms.ChoiceField(choices=(
        ('nomis_id', _('Prison')),
        ('count', _('Digital credits')),
        ('amount', _('Digital credit amount')),
    ), initial='nomis_id')


class PrisonCreditReportAdminView(BaseAdminReportView):
    title = _('Credits per-prison')
    template_name = 'admin/credit/credit/prison-report.html'
    form_class = PrisonCreditReportForm

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = context_data['form']

        prisons = Prison.objects \
            .exclude(nomis_id__in=self.excluded_nomis_ids) \
            .order_by() \
            .values_list('nomis_id', 'name')
        prisons = {
            nomis_id: {
                'name': prison,
                'nomis_id': nomis_id,
                'count': 0,
                'amount': 0,
            }
            for nomis_id, prison in prisons
        }

        since_date, until_date = form.period_date_range
        period_filters = {'received_at__date__gte': since_date}
        if until_date:
            period_filters['received_at__date__lt'] = until_date

        queryset = Credit.objects \
            .filter(
                resolution=CREDIT_RESOLUTION.CREDITED,
                **period_filters
            ) \
            .order_by() \
            .values('prison') \
            .annotate(count=models.Count('pk'), amount=models.Sum('amount')) \
            .values('prison', 'count', 'amount') \
            .order_by('prison')
        for row in queryset:
            if row['prison'] not in prisons:
                continue
            prisons[row['prison']].update(
                count=row['count'],
                amount=row['amount'],
            )

        prisons = prisons.values()
        ordering, reversed_order = form.get_ordering()
        prisons = sorted(
            prisons, key=lambda p: p[ordering] or 0,
            reverse=reversed_order
        )

        context_data['opts'] = Credit._meta
        context_data['form'] = form
        context_data['prisons'] = prisons
        return context_data
