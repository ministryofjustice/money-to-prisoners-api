from django import forms
from django.db import models
from django.db.models.functions import TruncMonth
from django.utils.translation import gettext_lazy as _

from core.forms import BasePeriodAdminReportForm, BasePrisonAdminReportForm
from core.views import BaseAdminReportView
from disbursement.models import Disbursement, DisbursementResolution
from prison.models import Prison


class DisbursementReportForm(BasePeriodAdminReportForm):
    pass


class DisbursementReportAdminView(BaseAdminReportView):
    title = _('Disbursement report')
    template_name = 'admin/disbursement/disbursement/report.html'
    form_class = DisbursementReportForm

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = context_data['form']

        current_period = form.current_period
        format_date = form.period_formatter

        rows = form.group_months_into_periods(self.get_monthly_rows())
        rows = list(filter(lambda r: r['date'] < current_period, rows))
        for row in rows:
            row['date_label'] = format_date(row['date'])
        context_data['rows'] = rows

        context_data['opts'] = Disbursement._meta
        context_data['form'] = form
        return context_data

    def get_monthly_rows(self):
        return Disbursement.objects \
            .filter(resolution=DisbursementResolution.sent) \
            .exclude(prison__in=self.excluded_nomis_ids) \
            .order_by() \
            .annotate(date=TruncMonth('created')) \
            .values('date') \
            .annotate(count=models.Count('pk'), amount=models.Sum('amount')) \
            .values('date', 'count', 'amount') \
            .order_by('date')


class PrisonDisbursementReportForm(BasePrisonAdminReportForm):
    ordering = forms.ChoiceField(choices=(
        ('nomis_id', _('Prison')),
        ('count', _('Digital disbursements')),
        ('amount', _('Digital disbursement amount')),
    ), initial='nomis_id')


class PrisonDisbursementReportAdminView(BaseAdminReportView):
    title = _('Disbursements per-prison')
    template_name = 'admin/disbursement/disbursement/prison-report.html'
    form_class = PrisonDisbursementReportForm

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = context_data['form']

        prisons = Prison.objects \
            .exclude(nomis_id__in=self.excluded_nomis_ids) \
            .exclude(private_estate=True) \
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
        period_filters = {'created__date__gte': since_date}
        if until_date:
            period_filters['created__date__lt'] = until_date

        queryset = Disbursement.objects \
            .filter(
                resolution=DisbursementResolution.sent,
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

        context_data['opts'] = Disbursement._meta
        context_data['form'] = form
        context_data['prisons'] = prisons
        return context_data
