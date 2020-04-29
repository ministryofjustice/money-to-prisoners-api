import json

from django.contrib import messages
from django.contrib.admin.models import LogEntry, ADDITION as ADDITION_LOG_ENTRY
from django.db import models
from django.urls import reverse_lazy
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from core.forms import DigitalTakeupReportForm, PrisonDigitalTakeupForm
from core.views import AdminViewMixin, BaseAdminReportView
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


class PrisonDigitalTakeupView(BaseAdminReportView):
    title = _('Digital take-up per prison')
    template_name = 'admin/performance/digitaltakeup/prison-report.html'
    form_class = PrisonDigitalTakeupForm

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
                'credits_by_post': 0,
                'credits_by_mtp': 0,
                'digital_takeup': None,
            }
            for nomis_id, prison in prisons
        }

        since_date, until_date = form.period_date_range
        period_filters = {'date__gte': since_date}
        if until_date:
            period_filters['date__lt'] = until_date

        takeup = DigitalTakeup.objects.filter(
            **period_filters
        ).values('prison').order_by('prison').annotate(
            credits_by_post=models.Sum('credits_by_post'),
            credits_by_mtp=models.Sum('credits_by_mtp'),
        )

        for row in takeup:
            if row['prison'] not in prisons:
                continue
            credits_by_post, credits_by_mtp = row['credits_by_post'], row['credits_by_mtp']
            if credits_by_post or credits_by_mtp:
                digital_takeup = credits_by_mtp / (credits_by_post + credits_by_mtp)
            else:
                digital_takeup = None
            prisons[row['prison']].update(
                credits_by_post=credits_by_post,
                credits_by_mtp=credits_by_mtp,
                digital_takeup=digital_takeup,
            )

        prisons = prisons.values()
        ordering, reversed_order = form.get_ordering()
        prisons = sorted(
            prisons, key=lambda p: p[ordering] or 0,
            reverse=reversed_order
        )

        context_data['opts'] = DigitalTakeup._meta
        context_data['form'] = form
        context_data['prisons'] = prisons
        return context_data


class DigitalTakeupReport(BaseAdminReportView):
    """
    Uses *reported* digital and postal credits to calculate digital take-up.
    Using this, the scaled/extrapolated postal credits are inferred from accurately counted credits.
    Gross savings = cost if all transactions were post - actual cost
                  = digital transactions * cost difference
    Uses trained curves for predicting future digital and postal credits and hence digital take-up and savings.
    """
    title = _('Digital take-up report')
    template_name = 'admin/performance/digitaltakeup/report.html'
    form_class = DigitalTakeupReportForm

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = context_data['form']

        exclude_private_estate = form.cleaned_data['private_estate'] == 'exclude'

        rows = form.group_months_into_periods(self.get_monthly_rows(exclude_private_estate))

        context_data['opts'] = DigitalTakeup._meta
        context_data['form'] = form
        context_data['exclude_private_estate'] = exclude_private_estate
        context_data['show_reported'] = form.cleaned_data['show_reported'] == 'show'
        context_data['show_savings'] = form.cleaned_data['show_savings'] == 'show'
        context_data['rows'] = list(self.process_rows(rows, form))

        context_data['show_predictions'] = form.cleaned_data['show_predictions'] == 'show'
        if context_data['show_predictions']:
            self.predict_rows(context_data['rows'], form, exclude_private_estate)

        context_data['chart_rows_json'] = self.process_chart_rows(context_data['rows'])
        return context_data

    def get_monthly_rows(self, exclude_private_estate):
        yield from DigitalTakeup.objects.digital_takeup_per_month(
            exclude_private_estate=exclude_private_estate
        )

    def process_rows(self, rows, form):
        current_period = form.current_period
        format_date = form.period_formatter
        cost_difference = form.cleaned_data['postal_cost'] - form.cleaned_data['digital_cost']

        for row in rows:
            if row['date'] >= current_period:
                break
            row.update(
                date_label=format_date(row['date']),
                predicted=False,
            )
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

    def predict_rows(self, rows, form, exclude_private_estate):
        from performance.prediction import date_to_curve_point, load_curve

        if not rows:
            return

        format_date = form.period_formatter
        scale_factor = form.prediction_scale
        cost_difference = form.cleaned_data['postal_cost'] - form.cleaned_data['digital_cost']

        if exclude_private_estate:
            key_suffix = 'without_private_estate'
        else:
            key_suffix = 'with_private_estate'
        predicted_credits_by_post = load_curve(f'extrapolated_credits_by_post_{key_suffix}')
        predicted_credits_by_mtp = load_curve(f'accurate_credits_by_mtp_{key_suffix}')

        last_date = rows[-1]['date']
        for period in form.get_periods_to_predict(last_date):
            x = date_to_curve_point(period)
            predicted_post = int(round(predicted_credits_by_post.get_value(x) * scale_factor))
            predicted_mtp = int(round(predicted_credits_by_mtp.get_value(x) * scale_factor))
            rows.append({
                'predicted': True,
                'date': period,
                'date_label': format_date(period),
                'reported_credits_by_post': None,
                'reported_credits_by_mtp': None,
                'extrapolated_credits_by_post': predicted_post,
                'accurate_credits_by_mtp': predicted_mtp,
                'digital_takeup': predicted_mtp / (predicted_post + predicted_mtp),
                'savings': predicted_mtp * cost_difference
            })

    def process_chart_rows(self, rows):
        return json.dumps([
            {'c': [
                {'v': row['date_label']},
                {'v': row['reported_credits_by_mtp']},
                {'v': row['reported_credits_by_post']},
                {'v': row['accurate_credits_by_mtp']},
                {'v': not row['predicted']},
                {'v': row['extrapolated_credits_by_post']},
                {'v': not row['predicted']},
            ]}
            for row in rows
        ], separators=(',', ':'))
