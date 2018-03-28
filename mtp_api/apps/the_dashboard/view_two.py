import datetime

from django.db import models
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView
import requests

from credit.models import Credit, CREDIT_RESOLUTION, CREDIT_STATUS
from core.views import AdminViewMixin
from disbursement.models import Disbursement, DISBURSEMENT_METHOD, DISBURSEMENT_RESOLUTION
from performance.models import DigitalTakeupQueryset, DigitalTakeup


def get_user_satisfaction():
    yearly_data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=1&period=year&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    yearly_data = yearly_data['data'][0]

    total_satisfied_each_year = yearly_data['rating_4:sum'] + yearly_data['rating_5:sum']
    total_not_satisfied_each_year = yearly_data['rating_1:sum'] + yearly_data['rating_2:sum'] + yearly_data['rating_3:sum']

    total = total_satisfied_each_year + total_not_satisfied_each_year
    try:
        return round((total_satisfied_each_year/total) * 100, 2)
    except ZeroDivisionError:
        return 'No rating'


def get_overall_stats(start_date, end_date):
    queryset_digital_credits = Credit.objects.filter(received_at__range=(start_date, end_date))
    queryset_disbursement = Disbursement.objects.filter(created__range=(start_date, end_date))
    stats = queryset_digital_credits.aggregate(credit_count=models.Count('id'), credit_amount=models.Sum('amount'))
    stats.update(
        queryset_disbursement.aggregate(disbursement_count=models.Count('id'), disbursement_amount=models.Sum('amount'))
    )
    return stats


def get_stats_by_method(start_date, end_date):
    credit_queryset = Credit.objects.filter(received_at__range=(start_date, end_date),
                                            resolution=CREDIT_RESOLUTION.CREDITED)
    credit_bank_transfer_count = credit_queryset.filter(transaction__isnull=False).count()
    credit_debit_card_count = credit_queryset.filter(payment__isnull=False).count()

    disbursement_queryset = Disbursement.objects.filter(created__range=(start_date, end_date),
                                                        resolution=DISBURSEMENT_RESOLUTION.SENT)
    disbursement_cheque_count = disbursement_queryset.filter(method=DISBURSEMENT_METHOD.CHEQUE).count()
    disbursement_bank_transfer_count = disbursement_queryset.filter(method=DISBURSEMENT_METHOD.BANK_TRANSFER).count()

    return {
        'debit_card_count': credit_debit_card_count,
        'bank_transfer_count': credit_bank_transfer_count,
        'disbursement_bank_transfer_count': disbursement_bank_transfer_count,
        'disbursement_cheque_count': disbursement_cheque_count,
    }


def transaction_by_post(the_digital_take_up, digital_transactions_count):
    if the_digital_take_up is not None:
        transaction_by_post = (1 - the_digital_take_up) * digital_transactions_count/the_digital_take_up
    else:
        transaction_by_post = 0

    return transaction_by_post


def get_transactions_by_post(start_of_month, end_of_month ):
    queryset_total_number_of_digital_transactions_in_month = Credit.objects.filter(received_at__range=(start_of_month, end_of_month))
    total_number_of_digital_transactions_in_month = queryset_total_number_of_digital_transactions_in_month.count()
    queryset_digital_take_up = DigitalTakeup.objects.filter(date__range=(start_of_month, end_of_month)).mean_digital_takeup()
    transaction_by_post_by_month = transaction_by_post(queryset_digital_take_up, total_number_of_digital_transactions_in_month)

    return round(transaction_by_post_by_month)


def get_savings(today):
    if today.month > 3:
        start_of_financial_year = today.replace(month=4, day=1)
        end_of_financial_year = today.replace(month=4, year= today.year+1, day=30)
    else:
        start_of_financial_year = today.replace(month=4, year=today.year-1, day=1)
        end_of_financial_year = today.replace(month=4, day=30)

    queryset_digital_transactions_this_financial_year = Credit.objects.filter(received_at__range=(start_of_financial_year, end_of_financial_year))
    digital_transactions_count_this_financial_year = queryset_digital_transactions_this_financial_year.count()

    COST_PER_TRANSACTION_BY_POST = 5.73
    COST_PER_TRANSACTION_BY_DIGITAL = 2.22

    queryset_digital_takeup_this_financial_year = DigitalTakeup.objects.filter(date__range=(start_of_financial_year, end_of_financial_year))
    digital_take_up_this_financial_year = queryset_digital_takeup_this_financial_year.mean_digital_takeup()

    transaction_by_post_this_financial_year = transaction_by_post(digital_take_up_this_financial_year, digital_transactions_count_this_financial_year)
    transaction_by_digital_this_financial_year = queryset_digital_transactions_this_financial_year.filter(resolution=CREDIT_RESOLUTION.CREDITED).count()

    total_cost_of_transaction_by_post = transaction_by_post_this_financial_year * COST_PER_TRANSACTION_BY_POST
    total_cost_of_transaction_by_digital = transaction_by_digital_this_financial_year * COST_PER_TRANSACTION_BY_DIGITAL
    total_cost_if_all_transactions_were_by_post = (transaction_by_post_this_financial_year + transaction_by_digital_this_financial_year) * COST_PER_TRANSACTION_BY_POST
    actual_cost = total_cost_of_transaction_by_post + total_cost_of_transaction_by_digital
    savings_made = total_cost_if_all_transactions_were_by_post - actual_cost

    return round(savings_made)


def get_previous_month(month, year):
    month -=1
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


class DashboardTwoView(AdminViewMixin, TemplateView):
    """
    Django admin view which presents an overview report for MTP
    """
    template_name = 'the_dashboard/dashboard_two.html'
    required_permissions = ['transaction.view_dashboard_two']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        weekday = today.weekday()

        start_delta = datetime.timedelta(days=weekday, weeks=1)
        start_of_previous_week = today - start_delta
        end_delta = datetime.timedelta(days=weekday)
        end_of_previous_week = today - end_delta
        month = today.month
        year = today.year
        last_year = year - 1
        last_month, last_months_year = get_previous_month(month, year)
        next_month, next_months_year = get_next_month(month, year)

        start_of_last_year = today.replace(month=1, year=last_year, day=1)
        start_of_previous_month = today.replace(month=last_month, year=last_months_year, day=1)
        start_of_current_month = today.replace(month=month, year=year, day=1)
        start_of_next_month = today.replace(month=next_month, year=next_months_year, day=1)
        start_of_current_year = today.replace(month=1, day=1)

        data, data_last_twelve_months = self.get_monthly_data(month, year)

        context['last_week'] = get_overall_stats(start_of_previous_week,  end_of_previous_week)
        context['this_week'] = get_overall_stats(end_of_previous_week, today)
        context['last_month'] = get_overall_stats(start_of_previous_month, start_of_current_month)
        context['this_month'] = get_overall_stats(start_of_current_month, start_of_next_month)
        context['last_year'] = get_overall_stats(start_of_last_year, start_of_current_year)
        context['this_year'] = get_overall_stats(start_of_current_year, today)
        context['data_last_twelve_months'] = data_last_twelve_months
        context['data'] = data
        context['savings'] =  get_savings(today)
        context['user_satisfaction'] = get_user_satisfaction()
        return context

    def get_monthly_data(self, month, year):
        data = []
        data_last_twelve_months = []
        tz = timezone.get_current_timezone()
        start_month, start_month_year = get_next_month(month, year)

        for count in range(12):
            next_month, next_month_year = start_month, start_month_year
            start_month, start_month_year = get_previous_month(start_month, start_month_year)
            start_of_month = make_first_of_month(start_month, start_month_year, tz)
            end_of_month = make_first_of_month(next_month, next_month_year, tz)

            transaction_by_post_by_month = get_transactions_by_post(start_of_month, end_of_month)
            stats_by_method = get_stats_by_method(start_of_month, end_of_month)
            if count < 6:
                stats_by_method['start_of_month'] = start_of_month
                stats_by_method['end_of_month'] = end_of_month
                stats_by_method['transaction_by_post'] = transaction_by_post_by_month

                data.append(stats_by_method)

            data_last_twelve_months.append({
                'start_of_month': start_of_month,
                'digital_take_up_count_each_month_last_twelve_months': stats_by_method['debit_card_count'] + stats_by_method['bank_transfer_count'],
                'transaction_by_post_count_each_month_last_twelve_months': transaction_by_post_by_month
            })

        return data, data_last_twelve_months
