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


def error_percentage(error, total ):
    try:
        return round((error/total) * 100, 2)
    except:
        return 0


def transaction_by_post(the_digital_take_up, digital_transactions_count):
    if the_digital_take_up is not None:
        transaction_by_post = (1 - the_digital_take_up) * digital_transactions_count
    else:
        transaction_by_post = 0

    return transaction_by_post

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
        last_year = year -1
        month = today.month
        last_month, last_months_year = get_previous_month(month, year)
        next_month, next_months_year = get_next_month(month, year)
        next_month_previous_year = next_months_year - 1

        start_of_current_month = today.replace(month=month, year=year, day=1)
        start_of_previous_month = today.replace(month=last_month, year=last_months_year, day=1)
        start_of_next_month = today.replace(month=next_month, year=next_months_year, day=1)
        start_of_current_month_last_year = today.replace(year=last_year, month=month, day=1)
        start_of_next_month_last_year = today.replace(year=next_month_previous_year, month=next_month, day=1)
        start_of_current_year = today.replace(month=1, day=1)

        queryset_digital_transactions_this_month = Credit.objects.filter(received_at__range=(start_of_current_month, start_of_next_month))
        queryset_digital_transactions_this_year = Credit.objects.filter(received_at__range=(start_of_current_year, today))
        queryset_digital_transactions_previous_week = Credit.objects.filter(received_at__range=(start_of_week, end_of_week))
        queryset_digital_takeup = DigitalTakeup.objects.filter(date__range=(start_of_current_year, today))

        queryset_disbursements_this_year = Disbursement.objects.filter(created__range=(start_of_current_year, today))
        queryset_disbursement_previous_week = Disbursement.objects.filter(created__range=(start_of_week, end_of_week))

        queryset_bank_transfer = Credit.objects.filter(transaction__isnull=False)
        queryset_debit_card = Credit.objects.filter(payment__isnull=False)
        queryset_debit_card_current_month = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_current_month, start_of_next_month))
        queryset_debit_card_current_month_last_year = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_current_month_last_year, start_of_next_month_last_year))

        queryset_disbursement_bank_transfer = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.BANK_TRANSFER)
        queryset_disbursement_cheque = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.CHEQUE)

        disbursement_amount_previous_week = queryset_disbursement_previous_week.aggregate(Sum('amount'))['amount__sum']
        disbursement_count_previous_week = queryset_disbursement_previous_week.count()
        disbursement_count_this_year = queryset_disbursements_this_year.count()
        disbursement_amount_this_year = queryset_disbursements_this_year.aggregate(Sum('amount'))['amount__sum']

        digital_transactions_amount_previous_week = queryset_digital_transactions_previous_week.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_previous_week = queryset_digital_transactions_previous_week.count()
        digital_transactions_count_this_month = queryset_digital_transactions_this_month.count()
        digital_transactions_amount_this_month = queryset_digital_transactions_this_month.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_this_year = queryset_digital_transactions_this_year.count()
        digital_transactions_amount_this_year = queryset_digital_transactions_this_year.aggregate(Sum('amount'))['amount__sum']

        digital_take_up_this_year = queryset_digital_takeup.mean_digital_takeup()
        transaction_by_post_this_year = transaction_by_post( digital_take_up_this_year, digital_transactions_count_this_year)

        transaction_by_digital = queryset_digital_transactions_this_year.filter(resolution=CREDIT_RESOLUTION.CREDITED).count()
        COST_PER_TRANSACTION_BY_POST = 5.73
        COST_PER_TRANSACTION_BY_DIGITAL = 2.22

        total_cost_of_transaction_by_post = transaction_by_post_this_year * COST_PER_TRANSACTION_BY_POST
        total_cost_of_transaction_by_digital = transaction_by_digital * COST_PER_TRANSACTION_BY_DIGITAL
        total_cost_if_it_was_only_by_post = (transaction_by_post_this_year + transaction_by_digital) * COST_PER_TRANSACTION_BY_POST
        actual_cost = total_cost_of_transaction_by_post + total_cost_of_transaction_by_digital
        savings_made = total_cost_if_it_was_only_by_post - actual_cost

        total_credit_this_month = queryset_debit_card_current_month.exclude(resolution=CREDIT_RESOLUTION.INITIAL)
        error_credit_this_month = total_credit_this_month.filter(transaction__isnull=False)
        total_credit_this_month_last_year = queryset_debit_card_current_month_last_year.exclude(resolution=CREDIT_RESOLUTION.INITIAL)
        error_credit_last_year = total_credit_this_month_last_year.filter(transaction__isnull=False)
        percent_of_errors_this_month = error_percentage(error_credit_this_month.count(), total_credit_this_month.count())
        percent_of_errors_this_month_last_year = error_percentage(error_credit_last_year.count(), total_credit_this_month_last_year.count())

        formated_previous_month_and_current_year = '{:%B %Y}'.format(start_of_previous_month)
        formated_current_month_and_year = '{:%B %Y}'.format(start_of_current_month)
        formated_current_month_last_year = '{:%B %Y}'.format(start_of_current_month_last_year)

        context['total_number_of_digital_transactions_this_month'] = digital_transactions_count_this_month
        context['total_amount_of_digital_transactions_this_month'] = digital_transactions_amount_this_month
        context['formated_previous_month_and_current_year'] = formated_previous_month_and_current_year
        context['formated_current_month_and_year'] = formated_current_month_and_year
        context['formated_current_month_last_year'] = formated_current_month_last_year
        context['percent_of_errors_last_month'] = percent_of_errors_this_month
        context['percent_of_errors_last_month_last_year'] = percent_of_errors_this_month_last_year
        context['savings_made'] = round(savings_made)
        context['number_of_disbursement_the_previous_week']= disbursement_count_previous_week
        context['total_amount_of_disbursement_previous_week'] = disbursement_amount_previous_week
        context['total_number_of_disbursement_this_year']= disbursement_count_this_year
        context['total_amount_of_disbursement_this_year'] = disbursement_amount_this_year
        context['total_number_of_digital_transactions_this_year'] = digital_transactions_count_this_year
        context['total_amount_of_digital_transactions_this_year'] =  digital_transactions_amount_this_year
        context['total_number_of_digital_transactions_recent_week']= digital_transactions_count_previous_week
        context['total_digital_amount_recent_week'] = digital_transactions_amount_previous_week


        transaction_by_post_current_month = None
        transaction_by_post_previous_month = None
        bank_transfer_count_current_month = None
        bank_transfer_count_previous_month = None
        debit_card_count_current_month = None
        debit_card_count_previous_month = None
        disbursement_amount_current_month = None
        disbursement_count_current_month = None
        digital_transactions_count_current_month = None
        digital_transactions_amount_current_month = None


        start_month, start_month_year = get_next_month(month, year)
        for _ in range(5):
            next_month, next_month_year = start_month, start_month_year
            start_month, start_month_year = get_previous_month(start_month, start_month_year)

            end_of_month = datetime.datetime(year=next_month_year, month=next_month, day=1)
            start_of_month = datetime.datetime(year=start_month_year, month=start_month, day=1)
            start_of_month = tz.localize(start_of_month)
            end_of_month = tz.localize(end_of_month)

            takeup_queryset = DigitalTakeup.objects.filter(date__range=(start_of_month, end_of_month))
            queryset_total_number_of_digital_transactions_in_month = Credit.objects.filter(received_at__range=(start_of_month, end_of_month))
            total_number_of_digital_transactions_in_month = queryset_total_number_of_digital_transactions_in_month.count()

            digital_take_up = takeup_queryset.mean_digital_takeup()
            transaction_by_post_by_month = transaction_by_post(digital_take_up, total_number_of_digital_transactions_in_month)

            bank_transfers = queryset_bank_transfer.filter(received_at__range=(start_of_month, end_of_month))
            debit_cards = queryset_debit_card.filter(received_at__range=(start_of_month, end_of_month))
            disbursement_bank_transfer = queryset_disbursement_bank_transfer.filter(created__range=(start_of_month, end_of_month))
            disbursement_cheque = queryset_disbursement_cheque.filter(created__range=(start_of_month, end_of_month))
            queryset_disbursement_all = Disbursement.objects.filter(created__range=(start_of_month, end_of_month))


            debit_card_amount = debit_cards.aggregate(Sum('amount'))['amount__sum'] or 0
            debit_card_count = debit_cards.count()
            bank_transfer_count = bank_transfers.count()
            bank_transfer_amount = bank_transfers.aggregate(Sum('amount'))['amount__sum'] or 0
            disbursement_bank_transfer_amount = disbursement_bank_transfer.aggregate(Sum('amount'))['amount__sum'] or 0
            disbursement_bank_transfer_count = disbursement_bank_transfer.count()
            disbursement_cheque_count = disbursement_cheque.count()
            disbursement_cheque_amount = disbursement_cheque.aggregate(Sum('amount'))['amount__sum'] or 0
            disbursement_count_all_methods = queryset_disbursement_all.count()
            disbursement_amount_all_methods = queryset_disbursement_all.aggregate(Sum('amount'))['amount__sum'] or 0


            if transaction_by_post_current_month is None:
                transaction_by_post_current_month = transaction_by_post_by_month

            elif transaction_by_post_previous_month is None:
                transaction_by_post_previous_month = transaction_by_post_by_month

            if bank_transfer_count_current_month is None:
                bank_transfer_count_current_month = bank_transfer_count

            elif bank_transfer_count_previous_month is None:
                bank_transfer_count_previous_month = bank_transfer_count

            if debit_card_count_current_month is None:
                debit_card_count_current_month = debit_card_count

            elif debit_card_count_previous_month is None:
                debit_card_count_previous_month = debit_card_count

            if disbursement_amount_current_month is None:
                disbursement_amount_current_month = disbursement_amount_all_methods

            if disbursement_count_current_month is None:
                disbursement_count_current_month = disbursement_count_all_methods


            data.append({
            'disbursement_bank_transfer_count': disbursement_bank_transfer_count,
            'disbursement_bank_transfer_amount': disbursement_bank_transfer_amount,
            'disbursement_cheque_count': disbursement_cheque_count,
            'disbursement_cheque_amount':disbursement_cheque_amount,
            'transaction_by_post':transaction_by_post_by_month,
            'transaction_count': bank_transfer_count,
            'credit_count': debit_card_count,
            'queryset_credit_amount': debit_card_amount,
            'queryset_transaction_amount': bank_transfer_amount,
            'start_of_month': start_of_month,
            'end_of_month': end_of_month,
            })

        context['previous_month_debit_card_count'] = debit_card_count_previous_month
        context['previous_month_bank_transfer_count'] = bank_transfer_count_previous_month
        context['previous_month_transaction_by_post'] = transaction_by_post_previous_month
        context['disbursement_count_current_month'] = disbursement_count_current_month
        context['disbursement_amount_current_month'] = disbursement_amount_current_month
        context['this_months_transaction_by_post'] = transaction_by_post_current_month
        context['this_months_bank_transfers'] =  bank_transfer_count_current_month
        context['this_month_debit'] = debit_card_count_current_month
        context['user_satisfaction'] = get_user_satisfaction()
        return context




