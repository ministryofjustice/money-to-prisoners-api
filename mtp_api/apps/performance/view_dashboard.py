import datetime

from django.db import models
from django.utils import timezone
from django.views.generic import TemplateView
import requests

from credit.models import Credit, CREDIT_RESOLUTION
from core.views import AdminViewMixin
from disbursement.constants import DisbursementResolution, DisbursementMethod
from disbursement.models import Disbursement
from performance.models import DigitalTakeup

COST_PER_TRANSACTION_BY_POST = 5.73
COST_PER_TRANSACTION_BY_DIGITAL = 2.22


def get_user_satisfaction():
    try:
        response = requests.get(
            'https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?'
            'flatten=true&duration=1&period=year&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&'
            'collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json'
        )
        response.raise_for_status()
    except requests.RequestException:
        return 'Not available'

    yearly_data = response.json()
    yearly_data = yearly_data['data'][0]

    total_satisfied_year = yearly_data['rating_4:sum'] + yearly_data['rating_5:sum']
    total_not_satisfied_year = yearly_data['rating_1:sum'] + yearly_data['rating_2:sum'] + yearly_data['rating_3:sum']

    total = total_satisfied_year + total_not_satisfied_year
    try:
        return round((total_satisfied_year/total) * 100)
    except ZeroDivisionError:
        return 'No rating'


def get_overall_stats(start_date, end_date):
    queryset_digital_credits = Credit.objects.filter(received_at__range=(start_date, end_date))
    queryset_disbursement = Disbursement.objects.filter(created__range=(start_date, end_date))
    stats = queryset_digital_credits.aggregate(credit_count=models.Count('id'), credit_amount=models.Sum('amount'))
    stats.update(
        queryset_disbursement.aggregate(disbursement_count=models.Count('id'),
                                        disbursement_amount=models.Sum('amount'))
    )
    return stats


def get_stats_by_method(start_date, end_date):
    credit_queryset = Credit.objects.filter(received_at__range=(start_date, end_date),
                                            resolution=CREDIT_RESOLUTION.CREDITED)
    credit_bank_transfer_count = credit_queryset.filter(transaction__isnull=False).count()
    credit_debit_card_count = credit_queryset.filter(payment__isnull=False).count()

    disbursement_queryset = Disbursement.objects.filter(created__range=(start_date, end_date),
                                                        resolution=DisbursementResolution.sent)
    disbursement_cheque_count = disbursement_queryset.filter(method=DisbursementMethod.cheque).count()
    disbursement_bank_transfer_count = disbursement_queryset.filter(method=DisbursementMethod.bank_transfer).count()

    return {
        'credit_debit_card_count': credit_debit_card_count,
        'credit_bank_transfer_count': credit_bank_transfer_count,
        'disbursement_bank_transfer_count': disbursement_bank_transfer_count,
        'disbursement_cheque_count': disbursement_cheque_count,
    }


def post_count(digital_take_up, digital_count):
    if digital_take_up is not None:
        post_count = (1 - digital_take_up) * digital_count/digital_take_up
    else:
        post_count = 0

    return post_count


def estimate_postal_credits(start_of_month, end_of_month):
    queryset_digital_month = Credit.objects.filter(received_at__range=(start_of_month, end_of_month))
    digital_month_count = queryset_digital_month.count()
    queryset_digital_take_up = DigitalTakeup.objects.filter(
        date__range=(start_of_month, end_of_month)).mean_digital_takeup()
    post_month = post_count(queryset_digital_take_up, digital_month_count)

    return int(round(post_month))


def savings_for_financial_year(today):
    if today.month > 3:
        start_financial_year = today.replace(month=4, day=1)
        end_financial_year = today.replace(month=4, year=today.year+1, day=30)
    else:
        start_financial_year = today.replace(month=4, year=today.year-1, day=1)
        end_financial_year = today.replace(month=4, day=30)

    queryset_digital = Credit.objects.filter(received_at__range=(start_financial_year, end_financial_year))
    digital_count = queryset_digital.count()

    queryset_digital_takeup = DigitalTakeup.objects.filter(date__range=(start_financial_year, end_financial_year))
    digital_takeup = queryset_digital_takeup.mean_digital_takeup()

    post = post_count(digital_takeup, digital_count)
    digital = queryset_digital.filter(resolution=CREDIT_RESOLUTION.CREDITED).count()

    total_cost_post = post * COST_PER_TRANSACTION_BY_POST
    total_cost_digital = digital * COST_PER_TRANSACTION_BY_DIGITAL
    total_cost_if_all_post = (post + digital) * COST_PER_TRANSACTION_BY_POST
    actual_cost = total_cost_post + total_cost_digital
    savings_made = total_cost_if_all_post - actual_cost

    return round(savings_made)


def get_previous_month(month, year):
    month -= 1
    if month == 0:
        month = 12
        year -= 1
    return month, year


def get_next_month(month, year):
    month += 1
    if month == 13:
        month = 1
        year += 1
    return month, year


def make_first_of_month(month, month_year, tz):
    month_and_year = datetime.datetime(year=month_year, month=month, day=1)
    month_and_year = tz.localize(month_and_year)

    return month_and_year


class PerformanceDashboardView(AdminViewMixin, TemplateView):
    """
    Django admin view which presents an overview report for MTP
    """
    template_name = 'performance/dashboard.html'
    required_permissions = ['transaction.view_dashboard']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        weekday = today.weekday()

        start_delta = datetime.timedelta(days=weekday, weeks=1)
        beginning_previous_week = today - start_delta
        end_delta = datetime.timedelta(days=weekday)
        end_previous_week = today - end_delta
        month = today.month
        year = today.year
        last_year = year - 1
        last_month, last_months_year = get_previous_month(month, year)
        next_month, next_months_year = get_next_month(month, year)

        beginning_last_year = today.replace(month=1, year=last_year, day=1)
        beginning_previous_month = today.replace(month=last_month, year=last_months_year, day=1)
        beginning_current_month = today.replace(month=month, year=year, day=1)
        beginning_next_month = today.replace(month=next_month, year=next_months_year, day=1)
        beginning_current_year = today.replace(month=1, day=1)

        data = self.get_monthly_data(last_month, last_months_year)

        context['last_week'] = get_overall_stats(beginning_previous_week,  end_previous_week)
        context['this_week'] = get_overall_stats(end_previous_week, today)
        context['last_month'] = get_overall_stats(beginning_previous_month, beginning_current_month)
        context['this_month'] = get_overall_stats(beginning_current_month, beginning_next_month)
        context['last_year'] = get_overall_stats(beginning_last_year, beginning_current_year)
        context['this_year'] = get_overall_stats(beginning_current_year, today)
        context['data'] = data
        context['data_six_months'] = data[0:7]
        context['savings'] = savings_for_financial_year(today)
        context['user_satisfaction'] = get_user_satisfaction()

        return context

    def get_monthly_data(self, month, year):
        data = []

        tz = timezone.get_current_timezone()
        start_month, start_month_year = get_next_month(month, year)

        for _ in range(12):
            next_month, next_month_year = start_month, start_month_year
            start_month, start_month_year = get_previous_month(start_month, start_month_year)
            start_of_month = make_first_of_month(start_month, start_month_year, tz)
            end_of_month = make_first_of_month(next_month, next_month_year, tz)

            post_by_month = estimate_postal_credits(start_of_month, end_of_month)
            stats_by_method = get_stats_by_method(start_of_month, end_of_month)

            stats_by_method['start_of_month'] = start_of_month
            stats_by_method['post_count'] = post_by_month
            stats_by_method['all_credits'] = (
                stats_by_method['credit_debit_card_count'] + stats_by_method['credit_bank_transfer_count']
            )

            data.append(stats_by_method)
        return data
