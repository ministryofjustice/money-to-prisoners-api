import collections
import datetime
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.models import LogEntry, ADDITION as ADDITION_LOG_ENTRY
from django.core.cache import cache
from django.db import models
from django.db.models.functions import TruncMonth
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
import requests
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from core.forms import (
    DigitalTakeupReportForm, PrisonDigitalTakeupForm,
    UserSatisfactionReportForm, ZendeskAdminReportForm,
)
from core.views import AdminViewMixin, BaseAdminReportView
from mtp_auth.permissions import SendMoneyClientIDPermissions
from oauth2_provider.models import Application
from performance.forms import DigitalTakeupUploadForm, UserSatisfactionUploadForm
from performance.models import DigitalTakeup, UserSatisfaction, PerformanceData
from performance.serializers import PerformanceDataSerializer
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
            .exclude(credit__prison__private_estate=True) \
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


class UserSatisfactionUploadView(AdminViewMixin, FormView):
    """
    Django admin view for uploading user satisfaction exported from GOV.UK Feedback Explorer
    """
    title = _('User satisfaction')
    form_class = UserSatisfactionUploadForm
    template_name = 'admin/performance/usersatisfaction/upload.html'
    success_url = reverse_lazy('admin:performance_usersatisfaction_changelist')
    required_permissions = ['performance.add_usersatisfaction', 'performance.change_usersatisfaction']

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['opts'] = UserSatisfaction._meta
        return context_data

    def form_valid(self, form):
        form.save()
        message = _('Saved user satisfaction records for %(count)d days') % {
            'count': len(form.records),
        }
        LogEntry.objects.log_action(
            user_id=self.request.user.pk,
            content_type_id=None, object_id=None,
            object_repr=message,
            action_flag=ADDITION_LOG_ENTRY,
        )
        messages.success(self.request, message)
        return super().form_valid(form)


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


class UserSatisfactionReport(BaseAdminReportView):
    """
    Django admin report view for showing user satisfaction exported from GOV.UK Feedback Explorer
    """
    title = _('User satisfaction report')
    template_name = 'admin/performance/usersatisfaction/report.html'
    form_class = UserSatisfactionReportForm

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = context_data['form']

        show_percentage = form.cleaned_data['display'] == 'percentage'

        current_period = form.current_period
        format_date = form.period_formatter

        rows = form.group_months_into_periods(self.get_monthly_rows())
        rows = filter(lambda r: r['date'] < current_period, rows)
        if show_percentage:
            def calc_percentage(r):
                total_count = sum(
                    rating_count
                    for rating_field, rating_count in r.items()
                    if rating_field in UserSatisfaction.rating_field_names
                )
                for rating_field in UserSatisfaction.rating_field_names:
                    if total_count:
                        r[rating_field] = r[rating_field] / total_count
                    else:
                        r[rating_field] = None
                return r

            rows = map(calc_percentage, rows)
        rows = list(rows)
        for row in rows:
            row['date_label'] = format_date(row['date'])
        context_data['rows'] = rows
        context_data['show_percentage'] = show_percentage

        context_data['opts'] = UserSatisfaction._meta
        context_data['form'] = form
        return context_data

    @classmethod
    def get_monthly_rows(cls):
        queryset = UserSatisfaction.objects \
            .order_by() \
            .annotate(month=TruncMonth('date')) \
            .values('month') \
            .annotate(**{
                field: models.Sum(field)
                for field in UserSatisfaction.rating_field_names
            }) \
            .values('month', *UserSatisfaction.rating_field_names) \
            .order_by('month')
        for row in queryset:
            row['date'] = timezone.make_aware(datetime.datetime.combine(
                row.pop('month'),
                datetime.time.min,
            ))
            yield row


class ZendeskReportAdminView(BaseAdminReportView):
    title = _('Zendesk report')
    template_name = 'performance/zendesk-report.html'
    form_class = ZendeskAdminReportForm

    cache_lifetime = 60 * 60 * 24  # 1 day

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = context_data['form']

        current_period = form.current_period
        format_date = form.period_formatter

        applications = list(Application.objects.order_by('name').values('name', 'client_id'))
        context_data['applications'] = applications

        rows = form.group_months_into_periods(self.get_monthly_rows(applications))
        rows = list(filter(lambda r: r['date'] < current_period, rows))
        for row in rows:
            row['date_label'] = format_date(row['date'])
            row['counts'] = [
                row[application['client_id']]
                for application in applications
            ]
        context_data['rows'] = rows

        return context_data

    def get_monthly_rows(self, applications):
        """
        Searches Zendesk for tickets tagged by application and environment to the beginning of 2 years ago
        """
        env_tag = settings.ENVIRONMENT

        end_date = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        for _m in range(end_date.month + 23):
            if end_date.month == 1:
                start_date = end_date.replace(year=end_date.year - 1, month=12)
            else:
                start_date = end_date.replace(month=end_date.month - 1)

            row = collections.defaultdict(int)
            row['date'] = start_date

            for application in applications:
                app_tag = application['client_id']
                row[app_tag] = self.get_ticket_count(env_tag, app_tag, start_date, end_date)

            yield row
            end_date = start_date

    def get_ticket_count(self, env_tag, app_tag, start_date, end_date):
        start_date = start_date.date().isoformat()
        end_date = end_date.date().isoformat()

        cache_key = f'zendesk_count_{env_tag}_{app_tag}_{start_date}'
        count = cache.get(cache_key)
        if count is not None:
            return count

        query = f'type:ticket created>="{start_date}" created<"{end_date}" tags:"{app_tag} {env_tag}"'
        try:
            response = requests.get(
                f'{settings.ZENDESK_BASE_URL}/api/v2/search/count.json',
                params={'query': query},
                auth=(f'{settings.ZENDESK_API_USERNAME}/token', settings.ZENDESK_API_TOKEN),
                timeout=15,
            )
            count = response.json().get('count', 0)
            cache.set(cache_key, count, timeout=self.cache_lifetime)
            return count
        except requests.RequestException:
            return 0


class PerformanceDataView(ListAPIView):
    serializer_class = PerformanceDataSerializer
    pagination_class = None

    permission_classes = (
        IsAuthenticated, SendMoneyClientIDPermissions,
    )

    def get_queryset(self):
        today = timezone.localdate()
        a_year_ago = today - datetime.timedelta(weeks=52)

        filters = {
            'week__gte': self.request.query_params.get('week__gte', a_year_ago),
            'week__lt': self.request.query_params.get('week__lt', today),
        }

        return PerformanceData.objects.filter(**filters)
