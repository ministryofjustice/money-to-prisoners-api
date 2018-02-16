import datetime
from django.shortcuts import render
from django.http import HttpResponse
from transaction.models import Transaction, TRANSACTION_CATEGORY, TRANSACTION_SOURCE, TRANSACTION_STATUS
from django.views.generic import FormView, TemplateView
from django.utils import timezone
from credit.models import Credit
from payment.models import Payment
from disbursement.models import Disbursement
from disbursement.constants import DISBURSEMENT_METHOD
from model_utils.models import TimeStampedModel
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

def get_user_satisfaction():
    monthly_data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=1&period=month&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    monthly_data = monthly_data["data"][0]
    weekly_data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=1&period=week&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    weekly_data = weekly_data["data"][0]
    yearly_data = requests.get('https://www.performance.service.gov.uk/data/send-prisoner-money/customer-satisfaction?flatten=true&duration=1&period=year&collect=rating_1%3Asum&collect=rating_2%3Asum&collect=rating_3%3Asum&collect=rating_4%3Asum&collect=rating_5%3Asum&collect=total%3Asum&format=json').json()
    yearly_data = yearly_data["data"][0]

    this_week = {}
    this_month = {}
    this_year = {}

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

    total_satisfied_each_week = weekly_ratings['rating_4'] + weekly_ratings['rating_5']
    total_satisfied_each_month =  monthly_ratings['rating_4'] + monthly_ratings['rating_5']
    total_satisfied_each_year = yearly_ratings['rating_4'] + yearly_ratings['rating_5']
    total_not_satisfied_each_week = weekly_ratings['rating_3'] + weekly_ratings['rating_2'] + weekly_ratings['rating_1']
    total_not_satisfied_each_month = monthly_ratings['rating_3'] + monthly_ratings['rating_2'] + monthly_ratings['rating_1']
    total_not_satisfied_each_year = yearly_ratings['rating_1'] + yearly_ratings['rating_2'] + yearly_ratings['rating_3']


    def percentage(total_satisfied, total_not_satisfied):
        total = total_satisfied + total_not_satisfied
        try:
            return round((total_satisfied/total) * 100, 2)
        except:
            return 'No rating'


    weekly_satisfaction_percentage = percentage(total_satisfied_each_week, total_not_satisfied_each_week)
    monthly_satisfaction_percentage = percentage(total_satisfied_each_month, total_not_satisfied_each_month)
    yearly_satisfaction_percentage = percentage(total_satisfied_each_year, total_not_satisfied_each_year)

    return {
        'weekly_ratings': weekly_satisfaction_percentage,
        'monthly_ratings': monthly_satisfaction_percentage,
        'yearly_ratings': yearly_satisfaction_percentage,
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
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        weekday = today.weekday()
        start_delta = datetime.timedelta(days=weekday, weeks=1)
        start_of_week = today - start_delta
        end_delta = datetime.timedelta(days=weekday)
        end_of_week = today - end_delta

        year = today.year
        last_year = today.year -1
        month = today.month
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1

        datetime.timedelta(days=weekday, weeks=1)

        starting_day_of_current_year = today.replace(month=1, day=1)

        def pence_to_pounds(amount):
            if(amount is None):
                return 0
            return amount/100


        queryset_total_number_of_digital_transactions_this_year = Credit.objects.filter(received_at__range=(starting_day_of_current_year, today))
        queryset_total_amount_of_digital_transactions_this_year = Credit.objects.filter(received_at__range=(starting_day_of_current_year, today)).aggregate(Sum('amount'))
        queryset_total_number_of_digital_transactions_previous_week = Credit.objects.filter(received_at__range=(start_of_week, end_of_week))
        queryset_amount_of_digital_transactions_previous_week = Credit.objects.filter(received_at__range=(start_of_week, end_of_week)).aggregate(Sum('amount'))

        queryset_number_of_disbursement_this_year = Disbursement.objects.filter(created__range=(starting_day_of_current_year, today))
        queryset_number_of_disbursement_previous_week = Disbursement.objects.filter(created__range=(start_of_week, end_of_week))
        queryset_disbursement_amount_this_year = Disbursement.objects.filter(created__range=(starting_day_of_current_year, today)).aggregate(Sum('amount'))
        queryset_disbursement_amount_this_week = Disbursement.objects.filter(created__range=(start_of_week, end_of_week)).aggregate(Sum('amount'))

        context['number_of_disbursement_the_previous_week']= queryset_number_of_disbursement_previous_week.count()
        context['number_of_disbursement_this_year']= queryset_number_of_disbursement_previous_week.count()
        context['disbursement_amount_previous_week'] = queryset_disbursement_amount_this_week['amount__sum']
        context['disbursement_amount_this_year'] = queryset_disbursement_amount_this_year['amount__sum']
        context['total_number_of_digital_transactions_this_year'] = queryset_total_number_of_digital_transactions_this_year.count()
        context['total_amount_of_digital_transactions_this_year'] = queryset_total_amount_of_digital_transactions_this_year['amount__sum']
        context['total_digital_transactions_recent_week']=  queryset_total_number_of_digital_transactions_previous_week.count()
        context['total_digital_amount_recent_week'] = queryset_amount_of_digital_transactions_previous_week['amount__sum']

        list_of_errors = []
        list_of_errors_the_previous_year = []
        list_of_transactions_by_post = []
        list_of_bank_transfer_count = []
        list_of_bank_transfer_amount = []
        list_of_debit_count = []
        list_of_debit_amount = []
        list_of_formated_months = []
        list_of_formated_months_last_year = []
        list_of_disbursement_in_months_amount = []
        list_of_disbursement_in_months_count = []

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

            queryset_bank_transfer = Credit.objects.filter(transaction__isnull=False).filter(received_at__range=(start_of_month, end_of_month))
            queryset_bank_transfer_amount = Credit.objects.filter(transaction__isnull=False).filter(received_at__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))
            queryset_debit = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_month, end_of_month))
            queryset_debit_amount = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))
            queryset_debit_last_year = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_month_last_year, end_of_month_last_year))

            queryset_number_of_all_digital_transactions = Credit.objects.filter(received_at__range=(start_of_month_last_year, end_of_month_last_year))
            queryset_amount_of_digital_transactions = Credit.objects.filter(received_at__range=(start_of_month_last_year, end_of_month_last_year)).aggregate(Sum('amount'))

            queryset_disbursement_bank_transfer_count = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.BANK_TRANSFER).filter(created__range=(start_of_month, end_of_month))
            queryset_disbursement_cheque_count = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.CHEQUE).filter(created__range=(start_of_month, end_of_month))
            queryset_disbursement_bank_transfer_amount = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.BANK_TRANSFER).filter(created__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))
            queryset_disbursement_cheque_amount = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.CHEQUE).filter(created__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))
            queryset_disbursement_count_all = Disbursement.objects.filter(created__range=(start_of_month, end_of_month))
            queryset_disbursement_amount_all = Disbursement.objects.filter(created__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))

            disbursement_amount_all = pence_to_pounds(queryset_disbursement_amount_all['amount__sum'])
            bank_transfer_amount_to_pounds = pence_to_pounds(queryset_bank_transfer_amount['amount__sum'])
            debit_amount_to_pounds = pence_to_pounds(queryset_debit_amount['amount__sum'])

            disbursement_cheque_amount_to_pounds = pence_to_pounds(queryset_disbursement_cheque_amount['amount__sum'])
            disbursement_bank_transfer_amount_to_pounds = pence_to_pounds(queryset_disbursement_bank_transfer_amount['amount__sum'])

            def error_percentage(error, total ):
                try:
                    return round((error/total) * 100, 2)
                except:
                    return 0

            takeup_queryset = DigitalTakeup.objects.filter(date__range=(start_of_month, end_of_month))

            transaction_by_post = 0
            for takeup in takeup_queryset:
                transaction_by_post += takeup.credits_by_post

            total_credit = queryset_debit.exclude(resolution=CREDIT_RESOLUTION.INITIAL)
            error_credit = total_credit.filter(transaction__isnull=False)

            total_credit_last_year = queryset_debit_last_year.exclude(resolution=CREDIT_RESOLUTION.INITIAL)
            error_credit_last_year = total_credit_last_year.filter(transaction__isnull=False)

            percent_of_errors = error_percentage(error_credit.count(), total_credit.count())
            percent_of_errors_last_year = error_percentage(error_credit_last_year.count(), total_credit_last_year.count())

            list_of_errors.append(percent_of_errors)
            list_of_errors_the_previous_year.append(percent_of_errors_last_year)
            list_of_transactions_by_post.append(transaction_by_post)
            list_of_bank_transfer_count.append(queryset_bank_transfer.count())
            list_of_debit_count.append(queryset_debit.count())
            list_of_formated_months.append(formated_month_and_year)
            list_of_formated_months_last_year.append(formated_months_last_year)
            list_of_debit_amount.append(queryset_debit_amount)
            list_of_bank_transfer_amount.append(queryset_bank_transfer_amount)
            list_of_disbursement_in_months_count.append(queryset_disbursement_count_all.count())
            list_of_disbursement_in_months_amount.append(disbursement_amount_all)


            data.append({
            'disbursement_bank_transfer_count':queryset_disbursement_bank_transfer_count.count(),
            'disbursement_bank_transfer_amount': disbursement_bank_transfer_amount_to_pounds,
            'disbursement_cheque_count': queryset_disbursement_cheque_count.count(),
            'disbursement_cheque_amount':disbursement_cheque_amount_to_pounds,
            'transaction_by_post':transaction_by_post,
            'transaction_count': queryset_bank_transfer.count(),
            'credit_count': queryset_debit.count(),
            'queryset_credit_amount': debit_amount_to_pounds,
            'queryset_transaction_amount': bank_transfer_amount_to_pounds,
            'start_of_month': start_of_month,
            'end_of_month': end_of_month,
            })

        current_month_transaction_amount = list_of_bank_transfer_amount[0]['amount__sum']
        current_month_credit_amount = list_of_debit_amount[0]['amount__sum']

        context['this_months_disbursement_in_months_amount'] = list_of_disbursement_in_months_amount[0]
        context['this_months_disbursement_in_months_count'] = list_of_disbursement_in_months_count[0]
        context['total_digital_amount_this_month'] = queryset_amount_of_digital_transactions['amount__sum']
        context['total_digital_transactions_this_month'] = queryset_number_of_all_digital_transactions.count()
        context['current_month_previous_year'] = list_of_formated_months_last_year[0]
        context['current_formated_month']= list_of_formated_months[0]
        context['this_months_transaction_by_post'] = list_of_transactions_by_post[0]
        context['this_months_bank_transfers'] = list_of_bank_transfer_count[0]
        context['this_month_debit'] = list_of_debit_count[0]
        context['last_year_same_time_percentage_of_errors'] = list_of_errors_the_previous_year[0]
        context['this_months_pecentage_of_errors'] = list_of_errors[0]
        context['last_months_percentage_of_errors'] = list_of_errors[1]
        context['user_satisfaction'] = get_user_satisfaction()
        return context




