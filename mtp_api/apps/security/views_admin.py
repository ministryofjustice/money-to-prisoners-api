import collections
import itertools
import logging

from django.db import models
from django.db.models.functions import TruncMonth
from django.utils.translation import gettext_lazy as _

from core.forms import BasePeriodAdminReportForm
from core.views import BaseAdminReportView
from credit.models import Credit
from security.models import Check

logger = logging.getLogger('mtp')


class CheckReportForm(BasePeriodAdminReportForm):
    pass


class CheckReportAdminView(BaseAdminReportView):
    title = _('Check report (for FIU)')
    template_name = 'admin/security/check/report.html'
    form_class = CheckReportForm

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

        context_data['opts'] = Check._meta
        context_data['form'] = form
        return context_data

    def get_monthly_rows(self):
        """
        Gets all credit count and amounts grouped by month and categorised by security check status.
        """
        # subquery used to determine if a credit's security check triggered any rules
        rules_triggered = Check.objects.filter(credit=models.OuterRef('pk'), rules__len__gte=1).values('pk')

        queryset = (
            # given all credits
            Credit.objects_all
            # take only credits since FIU checks went live
            # take only credits with a check (i.e. debit card payment was completed)
            .filter(created__date__gte='2020-01-02', security_check__status__isnull=False)
            # remove ordering
            .order_by()
            # truncate creation date and determine if associated check triggered rules
            # (subquery is not ideal, but django can't seem to group by array field length being >= 1)
            .annotate(date=TruncMonth('created'), triggered_rules=models.Exists(rules_triggered))
            .values('date', 'security_check__status', 'triggered_rules')
            # count credits and sum amounts
            .annotate(count=models.Count('pk'), amount=models.Sum('amount'))
            # group and order for display
            .values('date', 'security_check__status', 'triggered_rules', 'count', 'amount')
            .order_by('date', 'security_check__status', 'triggered_rules')
        )

        # collect counts and amounts into monthly rows
        grouped_rows = []
        for date, group in itertools.groupby(queryset, lambda r: r['date']):
            row = collections.defaultdict(int)
            row['date'] = date
            for item in group:
                count = item['count']
                amount = item['amount']
                status = item['security_check__status']
                triggered_rules = item['triggered_rules']
                if status == 'accepted':
                    if triggered_rules:
                        row['accepted_count'] += count
                        row['accepted_amount'] += amount
                    else:
                        row['auto_accepted_count'] += count
                        row['auto_accepted_amount'] += amount
                elif status == 'rejected' and triggered_rules:
                    row['rejected_count'] += count
                    row['rejected_amount'] += amount
                elif status == 'pending' and triggered_rules:
                    row['pending_count'] += count
                    row['pending_amount'] += amount
                else:
                    logger.warning(
                        'Unexpected grouped check status %(status)s with %(triggered_rules)s',
                        {'status': status, 'triggered_rules': triggered_rules}
                    )
            grouped_rows.append(row)

        return grouped_rows
