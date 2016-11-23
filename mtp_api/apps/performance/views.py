from django.contrib import messages
from django.contrib.admin.models import LogEntry, ADDITION as ADDITION_LOG_ENTRY
from django.core.urlresolvers import reverse_lazy
from django.db import models
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from core.views import AdminViewMixin
from performance.forms import DigitalTakeupUploadForm
from performance.models import DigitalTakeup


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
        self.check_takeup(form.start_date, form.end_date, form.credits_by_prison)
        form.save()
        LogEntry.objects.log_action(
            user_id=self.request.user.pk,
            content_type_id=None, object_id=None,
            object_repr=self.save_message % {
                'date': date_format(form.start_date, 'DATE_FORMAT'),
                'prison_count': len(form.credits_by_prison),
            },
            action_flag=ADDITION_LOG_ENTRY,
        )
        messages.success(self.request, self.save_message % {
            'date': date_format(form.start_date, 'DATE_FORMAT'),
            'prison_count': len(form.credits_by_prison),
        })
        return super().form_valid(form)

    def check_takeup(self, start_date, end_date, credits_in_spreadsheet):
        from credit.models import Log, LOG_ACTIONS

        credited = Log.objects.filter(created__date__range=(start_date, end_date),
                                      action=LOG_ACTIONS.CREDITED) \
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
                prison, credited[prison], credits_in_spreadsheet[prison][DigitalTakeupUploadForm.credit_type_mtp]
            )
            for prison in sorted(common_prison_credits)
            if credits_in_spreadsheet[prison][DigitalTakeupUploadForm.credit_type_mtp] != credited[prison]
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
