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

def weighted_average(data):
    rating_1 = data["rating_1:sum"]
    rating_2 = data["rating_2:sum"]
    rating_3 = data["rating_3:sum"]
    rating_4 = data["rating_4:sum"]
    rating_5 = data["rating_5:sum"]
    total_sum = data["total:sum"]

    return (0.25*rating_2 +.5*rating_3+rating_4*.75+rating_5)/(total_sum)


def get_user_satisfaction():
    data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=13&period=month&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    data = data["data"]
    today = datetime.date.today()
    year_of_last_month = today.year
    month_of_last_month = today.month - 1
    if (month_of_last_month == 0):
        year_of_last_month = year_of_last_month - 1
        month_of_last_month = 12

    year_of_previous_month = year_of_last_month
    month_of_previous_month = month_of_last_month -1
    if (month_of_previous_month == 0):
        year_of_previous_month = year_of_previous_month - 1
        month_of_previous_month = 12

    year_of_year_ago = year_of_last_month -1
    month_of_year_ago = month_of_last_month

    last_start = '%d-%02d' % (year_of_last_month, month_of_last_month)
    previous_start = '%d-%02d' % (year_of_previous_month, month_of_previous_month)
    year_ago_start = '%d-%02d' % (year_of_year_ago, month_of_year_ago)

    last = None
    previous = None
    year_ago = None
    for ratings in data:
        if ratings["_start_at"].startswith(last_start):
            last = weighted_average(ratings)
            last = "{:.2%}".format(last)

        if ratings["_start_at"].startswith(previous_start):
            previous = weighted_average(ratings)
            previous = "{:.2%}".format(previous)

        if ratings["_start_at"].startswith(year_ago_start):
            year_ago = weighted_average(ratings)
            year_ago = "{:.2%}".format(year_ago)



    return {
        'last': last,
        'previous': previous,
        'year_ago': year_ago
    }




class DashboardView(TemplateView):
    """
    Django admin view which presents an overview report for MTP
    """
    template_name = 'the_dashboard/digital_take_up.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = []
        context['data'] = data

        tz = timezone.get_current_timezone()
        today = datetime.date.today()
        year = today.year
        month = today.month
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1

        # url_satisfaction_data_not_sure = 'https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=52&period=week&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json'
        # url_satisfaction_data = "https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction"

        # satisfaction_data = ur.urlopen(url_satisfaction_data)
        # satisfaction_data = satisfaction_data.read()
        # # print(type(satisfaction_data))
        # satisfaction_data = satisfaction_data.decode('UTF-8')
        # # print(type(satisfaction_data))
        # satisfaction_data = json.loads(satisfaction_data)
        # # print(type(satisfaction_data))

        # satisfaction_data_list_of_dict = satisfaction_data['data']
        # print(satisfaction_data_list_of_dict)


        # def create_unique_data(data, sort_by):
        #     data_sorted = []
        #     for element in reversed(data):
        #         data_sorted.append(element[sort_by])
        #     return (set(data_sorted), sort_by)


        # # unique_data = create_unique_data(satisfaction_data_list_of_dict, '_month_start_at')

        # def create_data_object(unique_data, data):
        #     unique_data, sort_by = unique_data
        #     unique_data_list = list(unique_data)
        #     truncated_string_list = [string[:10] for string in unique_data_list]
        #     dict_data = {e: {'rating_1': 0, 'rating_2': 0, 'rating_3': 0, 'rating_4': 0, 'rating_5': 0 } for e in truncated_string_list}
        #     return dict_data




        # print(create_data_object(unique_data, satisfaction_data_list_of_dict))

        # print(create_data_object(create_unique_data, satisfaction_data_list_of_dict))

        # [li['total'] for li in data]

        # data_retrieve = [x if x['total'] == 52 for x in data]

        for _ in range(6):

            end_of_month = datetime.datetime(year=year, month=month, day=1)
            month -= 1
            if month == 0:
                month = 12
                year -= 1

            start_of_month = datetime.datetime(year=year, month=month, day=1)
            start_of_month = tz.localize(start_of_month)
            end_of_month = tz.localize(end_of_month)

            # print('start_of_month', start_of_month)
            # print('end_of_month', end_of_month)

            queryset_transaction = Transaction.objects.filter(received_at__range=(start_of_month, end_of_month))
            queryset_transaction_amount = Transaction.objects.filter(received_at__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))

            queryset_credit = Credit.objects.filter(received_at__range=(start_of_month, end_of_month))
            queryset_credit_amount = Credit.objects.filter(received_at__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))


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


            # transaction_by_post = [i.credits_by_post for i in digital_takeup]


            # def total_post(list_of_post_that_month):
            #     if(list_of_post_that_month == []):
            #         total = 0
                # else:
                #     total = functools.reduce(lambda x,y: x+y, list_of_post_that_month)
                #     total = sum(list_of_post_that_month)
            #     return total

            # transaction_by_post = total_post(transaction_by_post)


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

        context['user_satisfaction'] = get_user_satisfaction()
        return context




