from django.http import HttpResponse
from core.views import AdminViewMixin
from django.shortcuts import render
from django.views.generic import TemplateView
import requests
from django.http import HttpResponse
from performance.models import DigitalTakeupQueryset, DigitalTakeup
from django.utils import timezone
from credit.models import Credit
from credit.models import Credit, CREDIT_RESOLUTION, CREDIT_STATUS
import datetime
from disbursement.models import Disbursement
from django.db.models import Sum


def get_user_satisfaction():
    yearly_data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=1&period=year&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    yearly_data = yearly_data["data"][0]

    this_year = {}

    def ratings_data(time_span, ratings):
        ratings['rating_1'] = time_span['rating_1:sum']
        ratings['rating_2'] = time_span['rating_2:sum']
        ratings['rating_3'] = time_span['rating_3:sum']
        ratings['rating_4'] = time_span['rating_4:sum']
        ratings['rating_5'] = time_span['rating_5:sum']
        return ratings


    yearly_ratings = ratings_data(yearly_data, this_year)

    total_satisfied_each_year = yearly_ratings['rating_4'] + yearly_ratings['rating_5']
    total_not_satisfied_each_year = yearly_ratings['rating_1'] + yearly_ratings['rating_2'] + yearly_ratings['rating_3']


    def percentage(total_satisfied, total_not_satisfied):
        total = total_satisfied + total_not_satisfied
        try:
            return round((total_satisfied/total) * 100, 2)
        except:
            return 'No rating'


    yearly_satisfaction_percentage = percentage(total_satisfied_each_year, total_not_satisfied_each_year)

    return yearly_satisfaction_percentage


def transaction_by_post(the_digital_take_up, digital_transactions_count):
    if the_digital_take_up is not None:
        transaction_by_post = (1 - the_digital_take_up) * digital_transactions_count
    else:
        transaction_by_post = 0

    return transaction_by_post


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
        start_of_week = today - start_delta
        end_delta = datetime.timedelta(days=weekday)
        end_of_week = today - end_delta
        month = today.month
        year = today.year
        last_month, last_months_year = get_previous_month(month, year)
        next_month, next_months_year = get_next_month(month, year)

        start_of_previous_month = today.replace(month=last_month, year=last_months_year, day=1)
        start_of_current_month = today.replace(month=month, year=year, day=1)
        start_of_next_month = today.replace(month=next_month, year=next_months_year, day=1)
        start_of_current_year = today.replace(month=1, day=1)

        queryset_digital_transactions_this_year = Credit.objects.filter(received_at__range=(start_of_current_year, today))
        digital_transactions_count_this_year = queryset_digital_transactions_this_year.count()

        queryset_digital_transactions_this_month = Credit.objects.filter(received_at__range=(start_of_current_month, start_of_next_month))
        queryset_digital_transactions_this_year = Credit.objects.filter(received_at__range=(start_of_current_year, today))
        queryset_digital_transactions_previous_week = Credit.objects.filter(received_at__range=(start_of_week, end_of_week))

        queryset_disbursements_this_year = Disbursement.objects.filter(created__range=(start_of_current_year, today))
        queryset_disbursement_previous_week = Disbursement.objects.filter(created__range=(start_of_week, end_of_week))
        queryset_disbursement_this_month = Disbursement.objects.filter(created__range=(start_of_current_month, start_of_next_month))
        queryset_disbursement_last_month = Disbursement.objects.filter(created__range=(start_of_previous_month, start_of_current_month))

        disbursement_count_previous_week = queryset_disbursement_previous_week.count()
        disbursement_amount_previous_week = queryset_disbursement_previous_week.aggregate(Sum('amount'))['amount__sum']
        disbursement_count_this_month = queryset_disbursement_this_month.count()
        disbursement_amount_this_month = queryset_disbursement_this_month.aggregate(Sum('amount'))['amount__sum'] or 0
        disbursement_count_last_month = queryset_disbursement_last_month.count()
        disbursement_amount_last_month = queryset_disbursement_last_month.aggregate(Sum('amount'))['amount__sum'] or 0
        disbursement_count_this_year = queryset_disbursements_this_year.count()
        disbursement_amount_this_year = queryset_disbursements_this_year.aggregate(Sum('amount'))['amount__sum']

        digital_transactions_amount_previous_week = queryset_digital_transactions_previous_week.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_previous_week = queryset_digital_transactions_previous_week.count()
        digital_transactions_count_this_month = queryset_digital_transactions_this_month.count()
        digital_transactions_amount_this_month = queryset_digital_transactions_this_month.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_this_year = queryset_digital_transactions_this_year.count()
        digital_transactions_amount_this_year = queryset_digital_transactions_this_year.aggregate(Sum('amount'))['amount__sum']





        context['disbursement_count_previous_week']= disbursement_count_previous_week
        context['disbursement_amount_previous_week'] = disbursement_amount_previous_week
        context['disbursement_count_this_month'] = disbursement_count_this_month
        context['disbursement_amount_this_month'] = disbursement_amount_this_month
        context['disbursement_count_last_month'] = disbursement_count_last_month
        context['disbursement_amount_last_month'] = disbursement_amount_last_month
        context['disbursement_count_this_year']= disbursement_count_this_year
        context['disbursement_amount_this_year'] = disbursement_amount_this_year
        context['digital_transactions_amount_previous_week'] = digital_transactions_amount_previous_week
        context['digital_transactions_count_previous_week']= digital_transactions_count_previous_week
        context['digital_transactions_count_this_month'] = digital_transactions_count_this_month
        context['digital_transactions_amount_this_month'] = digital_transactions_amount_this_month
        context['digital_transactions_count_this_year'] = digital_transactions_count_this_year
        context['digital_transactions_amount_this_year'] =  digital_transactions_amount_this_year

        context['savings'] =  self.get_savings(start_of_current_year, today, digital_transactions_count_this_year, queryset_digital_transactions_this_year)
        context['user_satisfaction'] = get_user_satisfaction()
        return context

    def get_savings(self, start_of_current_year, today, digital_transactions_count_this_year, queryset_digital_transactions_this_year):
        COST_PER_TRANSACTION_BY_POST = 5.73
        COST_PER_TRANSACTION_BY_DIGITAL = 2.22

        queryset_digital_takeup = DigitalTakeup.objects.filter(date__range=(start_of_current_year, today))
        digital_take_up_this_year = queryset_digital_takeup.mean_digital_takeup()

        transaction_by_post_this_year = transaction_by_post(digital_take_up_this_year, digital_transactions_count_this_year)
        transaction_by_digital_this_year = queryset_digital_transactions_this_year.filter(resolution=CREDIT_RESOLUTION.CREDITED).count()

        total_cost_of_transaction_by_post = transaction_by_post_this_year * COST_PER_TRANSACTION_BY_POST
        total_cost_of_transaction_by_digital = transaction_by_digital_this_year * COST_PER_TRANSACTION_BY_DIGITAL
        total_cost_if_all_transactions_were_by_post = (transaction_by_post_this_year + transaction_by_digital_this_year) * COST_PER_TRANSACTION_BY_POST
        actual_cost = total_cost_of_transaction_by_post + total_cost_of_transaction_by_digital
        savings_made = total_cost_if_all_transactions_were_by_post - actual_cost

        return round(savings_made)


