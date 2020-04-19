from django import forms
from django.db import models
from django.db.models.functions import TruncMonth
from django.utils.translation import gettext_lazy as _

from core.forms import BasePeriodAdminReportForm
from core.views import AdminReportView
from credit.models import Credit, CREDIT_RESOLUTION


class CreditReportForm(BasePeriodAdminReportForm):
    private_estate = forms.ChoiceField(label=_('Private estate'), choices=(
        ('include', _('Include')),
        ('exclude', _('Exclude')),
    ), initial='include')


class CreditReportAdminView(AdminReportView):
    title = _('Credit report')
    template_name = 'admin/credit/credit/report.html'
    form_class = CreditReportForm
    required_permissions = ['transaction.view_dashboard']
    excluded_nomis_ids = {'ZCH'}

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
