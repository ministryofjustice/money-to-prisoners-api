from datetime import date, timedelta

from django.contrib import messages
from django.contrib.admin.models import LogEntry, ADDITION as ADDITION_LOG_ENTRY
from django.db import models
from django.urls import reverse_lazy
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

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

        days_in_past = int(self.request.GET.get('days') or 30)
        context_data['days_in_past'] = days_in_past
        since_date = date.today() - timedelta(days=days_in_past)

        prisons = Prison.objects.exclude(
            nomis_id__in=self.excluded_nomis_ids
         ).values_list('nomis_id', 'name')

        prisons = {
            nomis_id: {
                'name': prison,
                'disbursement_count': 0,
                'credit_post_count': None,
                'credit_mtp_count': None,
                'credit_uptake': None,
            }
            for nomis_id, prison in prisons
         }

        disbursements = Disbursement.objects.exclude(
            prison__in=self.excluded_nomis_ids,
            resolution=DISBURSEMENT_RESOLUTION.SENT, created__date__gte=since_date,
        ).values('prison').order_by('prison').annotate(count=models.Count('*'))
        for row in disbursements:
            prisons[row['prison']]['disbursement_count'] = row['count']

        takeup = DigitalTakeup.objects.filter(
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
        order_by = 'nomis_id'
        if (
            'order_by' in self.request.GET and
            self.request.GET['order_by'] in self.ordering_fields
        ):
            order_by = self.request.GET.get('order_by')

        prisons = sorted(
            prisons, key=lambda p: p.get(order_by) or 0,
            reverse=int(self.request.GET.get('desc', 0))
        )

        context_data['prisons'] = prisons
        return context_data
