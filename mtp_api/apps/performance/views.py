from datetime import date, timedelta

from django.contrib import messages
from django.contrib.admin.models import LogEntry, ADDITION as ADDITION_LOG_ENTRY
from django.db import models
from django.urls import reverse_lazy
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from core.views import AdminViewMixin
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

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        days_in_past = int(self.request.GET.get('days') or 30)
        context_data['days_in_past'] = days_in_past

        prison_disbursements = Prison.objects.annotate(
            disbursement_count=models.Count('disbursement')
        ).filter(
            models.Q(disbursement_count=0) |
            models.Q(disbursement__created__gte=date.today() - timedelta(days=days_in_past))
        ).annotate(
            disbursement_count=models.Count('disbursement')
        ).order_by('nomis_id').distinct()

        prison_takeup = Prison.objects.all().annotate(
            digitaltakeup_count=models.Count('digitaltakeup')
        ).filter(
            models.Q(digitaltakeup_count=0) |
            models.Q(digitaltakeup__date__gte=date.today() - timedelta(days=days_in_past))
        ).annotate(
            credit_post_count=models.Sum('digitaltakeup__credits_by_post'),
            credit_mtp_count=models.Sum('digitaltakeup__credits_by_mtp')
        ).order_by('nomis_id').distinct()

        for i, prison in enumerate(prison_takeup):
            prison.disbursement_count = prison_disbursements[i].disbursement_count
            if prison.credit_mtp_count or prison.credit_post_count:
                prison.credit_uptake = (
                    prison.credit_mtp_count /
                    (prison.credit_mtp_count + prison.credit_post_count)
                )

        if (
            'order_by' in self.request.GET and
            self.request.GET['order_by'] in self.ordering_fields
        ):
            order_by = self.request.GET['order_by']
            prison_takeup = sorted(
                prison_takeup, key=lambda p: getattr(p, order_by, None) or 0,
                reverse=int(self.request.GET.get('desc', 0))
            )

        context_data['prisons'] = prison_takeup
        return context_data
