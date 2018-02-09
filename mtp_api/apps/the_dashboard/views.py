import datetime

from django.shortcuts import render

from django.http import HttpResponse
from transaction.models import Transaction, TRANSACTION_CATEGORY, TRANSACTION_SOURCE, TRANSACTION_STATUS
from django.views.generic import FormView, TemplateView
from django.utils import timezone
from credit.models import Credit
from payment.models import Payment
from performance.models import DigitalTakeupQueryset, DigitalTakeup
from django.db.models import Sum
import pytz
import functools
import urllib.request as ur
import json
import requests
from django.db import models
from credit.models import Credit, CREDIT_RESOLUTION, CREDIT_STATUS


TRANSACTION_ERROR_FILTERS = (
    models.Q(transaction__source=TRANSACTION_SOURCE.BANK_TRANSFER,
             prison__isnull=True) |
    models.Q(transaction__source=TRANSACTION_SOURCE.BANK_TRANSFER,
             blocked=True)
)

# def weighted_average(data):
#     rating_1 = data["rating_1:sum"]
#     rating_2 = data["rating_2:sum"]
#     rating_3 = data["rating_3:sum"]
#     rating_4 = data["rating_4:sum"]
#     rating_5 = data["rating_5:sum"]
#     total_sum = data["total:sum"]

#     return (0.25*rating_2 +.5*rating_3+rating_4*.75+rating_5)/(total_sum)


def get_user_satisfaction():
    monthly_data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=1&period=month&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    monthly_data = monthly_data["data"][0]
    weekly_data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=1&period=week&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    weekly_data = weekly_data["data"][0]
    yearly_data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=1&period=year&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    yearly_data = yearly_data["data"][0]

    this_week = {'rating_1': 0, 'rating_2': 0, 'rating_3': 0, 'rating_4': 0, 'rating_5': 0}
    this_month = {'rating_1': 0, 'rating_2': 0, 'rating_3': 0, 'rating_4': 0, 'rating_5': 0}
    this_year = {'rating_1': 0, 'rating_2': 0, 'rating_3': 0, 'rating_4': 0, 'rating_5': 0}

    def ratings_data(time_span, ratings):
        ratings['rating_1'] = time_span['rating_1:sum']
        ratings['rating_2'] = time_span['rating_2:sum']
        ratings['rating_3'] = time_span['rating_3:sum']
        ratings['rating_4'] = time_span['rating_4:sum']
        ratings['rating_5'] = time_span['rating_5:sum']
        return ratings

    weekly_ratings = ratings_data(weekly_data, this_week)
    monthly_ratings = ratings_data(monthly_data, this_month)
    yearly_ratings = ratings_data(yearly_data, this_year)

    # print(ratings)

    # today = datetime.date.today()
    # year_of_last_month = today.year
    # month_of_last_month = today.month - 1
    # if (month_of_last_month == 0):
    #     year_of_last_month = year_of_last_month - 1
    #     month_of_last_month = 12

    # year_of_previous_month = year_of_last_month
    # month_of_previous_month = month_of_last_month -1
    # if (month_of_previous_month == 0):
    #     year_of_previous_month = year_of_previous_month - 1
    #     month_of_previous_month = 12

    # year_of_year_ago = year_of_last_month -1
    # month_of_year_ago = month_of_last_month

    # last_start = '%d-%02d' % (year_of_last_month, month_of_last_month)
    # previous_start = '%d-%02d' % (year_of_previous_month, month_of_previous_month)
    # year_ago_start = '%d-%02d' % (year_of_year_ago, month_of_year_ago)

    # last = None
    # previous = None
    # year_ago = None
    # for ratings in data:
    #     if ratings["_start_at"].startswith(last_start):
    #         last = weighted_average(ratings)
    #         last = "{:.2%}".format(last)

    #     if ratings["_start_at"].startswith(previous_start):
    #         previous = weighted_average(ratings)
    #         previous = "{:.2%}".format(previous)

    #     if ratings["_start_at"].startswith(year_ago_start):
    #         year_ago = weighted_average(ratings)
    #         year_ago = "{:.2%}".format(year_ago)

    return {
        'weekly_ratings': weekly_ratings,
        'monthly_ratings': monthly_ratings,
        'yearly_ratings': yearly_ratings
    }


class DashboardView(TemplateView):
    """
    Django admin view which presents an overview report for MTP
    """
    template_name = 'the_dashboard/the_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = []
        context['data'] = data

        tz = timezone.get_current_timezone()
        today = datetime.date.today()
        year = today.year
        last_year = today.year -1
        print("LAST YEAR", last_year)
        month = today.month
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1

        list_of_errors = []
        list_of_errors_the_previous_year = []
        list_of_transactions_by_post = []
        list_of_transaction_count = []
        list_of_credit_count = []
        list_of_formated_months = []
        list_of_formated_months_last_year = []

        for _ in range(5):
            end_of_month = datetime.datetime(year=year, month=month, day=1)
            end_of_month_last_year = datetime.datetime(year=last_year, month=month, day=1)
            month -= 1
            if month == 0:
                month = 12
                year -= 1
                last_year -= 1

            start_of_month_last_year = datetime.datetime(year=last_year, month=month, day=1)
            start_of_month = datetime.datetime(year=year, month=month, day=1)
            start_of_month = tz.localize(start_of_month)
            end_of_month = tz.localize(end_of_month)
            start_of_month_last_year = tz.localize(start_of_month_last_year)
            end_of_month_last_year = tz.localize(end_of_month_last_year)
            formated_month_and_year = '{:%B %Y}'.format(start_of_month)
            formated_months_last_year = '{:%B %Y}'.format(start_of_month_last_year)

            queryset_transaction = Transaction.objects.filter(received_at__range=(start_of_month, end_of_month))
            queryset_transaction_amount = Transaction.objects.filter(received_at__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))

            queryset_credit = Credit.objects.filter(received_at__range=(start_of_month, end_of_month))
            queryset_credit_amount = Credit.objects.filter(received_at__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))

            queryset_credit_last_year = Credit.objects.filter(received_at__range=(start_of_month_last_year, end_of_month_last_year))

            def pence_to_pounds(amount):
                if(amount == None):
                    return 0
                if(amount != None):
                    return amount/100

            amount_transaction_to_pounds = pence_to_pounds(queryset_transaction_amount['amount__sum'])
            amount_credit_to_pounds = pence_to_pounds(queryset_credit_amount['amount__sum'])

            def as_a_percentage(credit, transaction, post=0):
                if(credit == None):
                     credit = 0
                if(transaction == None):
                    transaction = 0
                if(post == None):
                    post = 0
                if(credit == 0 and transaction == 0 and post == 0 ):
                    percent = {'percent_of_credit': 0, 'percent_of_transaction': 0, 'percent_of_post': 0}
                else:
                    total = credit + transaction + post
                    percent_of_credit = credit/total * 100
                    percent_of_transaction = transaction/total * 100
                    percent_of_post = post/total * 100
                    percent = {'percent_of_credit': round(percent_of_credit, 2), 'percent_of_transaction': round(percent_of_transaction, 2), 'percent_of_post': round(percent_of_post, 2)}
                return percent

            percent_of_use = as_a_percentage(queryset_credit.count(), queryset_transaction.count())
            percent_of_amount = as_a_percentage(queryset_credit_amount['amount__sum'], queryset_transaction_amount['amount__sum'])

            takeup_queryset = DigitalTakeup.objects.filter(date__range=(start_of_month, end_of_month))
            transaction_by_post = 0
            for takeup in takeup_queryset:
                transaction_by_post += takeup.credits_by_post


            total_credit = queryset_credit.exclude(resolution=CREDIT_RESOLUTION.INITIAL)
            error_credit = total_credit.filter(transaction__isnull=False)
            total_credit_count = total_credit.count()
            error_credit_count = error_credit.count()

            total_credit_last_year = queryset_credit_last_year.exclude(resolution=CREDIT_RESOLUTION.INITIAL)
            error_credit_last_year = total_credit_last_year.filter(transaction__isnull=False)
            total_credit_count_last_year = total_credit_last_year.count()
            error_credit_count_last_year = error_credit_last_year.count()


            def error_percentage(total, errors):
                try:
                    percent_of_errors = (errors/total) * 100
                except:
                    percent_of_errors = 0
                return round(percent_of_errors)

            percent_of_errors = error_percentage(total_credit_count, error_credit_count)

            percent_of_errors_last_year = error_percentage(total_credit_count_last_year, error_credit_count_last_year)

            list_of_errors.append(percent_of_errors)
            list_of_errors_the_previous_year.append(percent_of_errors_last_year)
            list_of_transactions_by_post.append(transaction_by_post)
            list_of_transaction_count.append(queryset_transaction.count())
            list_of_credit_count.append(queryset_credit.count())
            list_of_formated_months.append(formated_month_and_year)
            list_of_formated_months_last_year.append(formated_months_last_year)

            data.append({
            'transaction_by_post':transaction_by_post,
            'transaction_count': queryset_transaction.count(),
            'credit_count': queryset_credit.count(),
            'queryset_credit_amount': amount_credit_to_pounds,
            'queryset_transaction_amount': amount_transaction_to_pounds,
            'percent_of_credit_count': percent_of_use['percent_of_credit'],
            'percent_of_transaction_count': percent_of_use['percent_of_transaction'],
            'percent_credit_amount': percent_of_amount['percent_of_credit'],
            'percent_of_post': percent_of_amount['percent_of_post'],
            'percent_transaction_amount': percent_of_amount['percent_of_transaction'],
            'start_of_month': start_of_month,
            'end_of_month': end_of_month,
            })
        this_months_transaction_by_post = list_of_transactions_by_post[0]
        this_months_transaction = list_of_transaction_count[0]
        this_month_credit = list_of_credit_count[0]

        last_year_same_time_percentage_of_errors = list_of_errors_the_previous_year[0]
        this_months_pecentage_of_errors = list_of_errors[0]
        last_months_percentage_of_errors = list_of_errors[1]
        current_formated_month = list_of_formated_months[0]
        current_month_previous_year = list_of_formated_months_last_year[0]

        context['current_month_previous_year'] = current_month_previous_year
        context['current_formated_month']= current_formated_month
        context['this_months_transaction_by_post'] = this_months_transaction_by_post
        context['this_months_transaction'] = this_months_transaction
        context['this_month_credit'] = this_month_credit
        context['last_year_same_time_percentage_of_errors'] = last_year_same_time_percentage_of_errors
        context['this_months_pecentage_of_errors'] = this_months_pecentage_of_errors
        context['last_months_percentage_of_errors'] = last_months_percentage_of_errors
        context['user_satisfaction'] = get_user_satisfaction()
        return context




