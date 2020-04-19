from django.db import models
from django.db.models.functions import TruncMonth
from django.utils.translation import gettext_lazy as _

from core.forms import BasePeriodAdminReportForm
from core.views import AdminReportView
from disbursement.models import Disbursement, DISBURSEMENT_RESOLUTION


class DisbursementReportForm(BasePeriodAdminReportForm):
    pass


class DisbursementReportAdminView(AdminReportView):
    title = _('Disbursement report')
    template_name = 'admin/disbursement/disbursement/report.html'
    form_class = DisbursementReportForm
    required_permissions = ['transaction.view_dashboard']

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
            .filter(resolution=DISBURSEMENT_RESOLUTION.SENT) \
            .order_by() \
            .annotate(date=TruncMonth('created')) \
            .values('date') \
            .annotate(count=models.Count('pk'), amount=models.Sum('amount')) \
            .values('date', 'count', 'amount') \
            .order_by('date')
