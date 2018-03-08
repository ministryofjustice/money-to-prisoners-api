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


def get_transactions_by_post(start_of_month, end_of_month ):
    queryset_total_number_of_digital_transactions_in_month = Credit.objects.filter(received_at__range=(start_of_month, end_of_month))
    total_number_of_digital_transactions_in_month = queryset_total_number_of_digital_transactions_in_month.count()
    queryset_digital_take_up = DigitalTakeup.objects.filter(date__range=(start_of_month, end_of_month)).mean_digital_takeup()
    transaction_by_post_by_month = transaction_by_post(queryset_digital_take_up, total_number_of_digital_transactions_in_month)

    return transaction_by_post_by_month


def get_disbursements(start_of_month, end_of_month):
    queryset_disbursement_bank_transfer = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.BANK_TRANSFER).filter(created__range=(start_of_month, end_of_month))
    disbursement_bank_transfer_amount = queryset_disbursement_bank_transfer.aggregate(Sum('amount'))['amount__sum'] or 0
    disbursement_bank_transfer_count = queryset_disbursement_bank_transfer.count()

    return (disbursement_bank_transfer_amount, disbursement_bank_transfer_count)


def get_disbursements_by_check(start_of_month, end_of_month):
    queryset_disbursement_cheque = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.CHEQUE).filter(created__range=(start_of_month, end_of_month))
    disbursement_cheque_count = queryset_disbursement_cheque.count()
    disbursement_cheque_amount = queryset_disbursement_cheque.aggregate(Sum('amount'))['amount__sum'] or 0

    return (disbursement_cheque_count, disbursement_cheque_amount)


def get_bank_transfers(start_of_month, end_of_month):
    queryset_bank_transfer = Credit.objects.filter(transaction__isnull=False).filter(received_at__range=(start_of_month, end_of_month))
    bank_transfer_count = queryset_bank_transfer.count()
    bank_transfer_amount = queryset_bank_transfer.aggregate(Sum('amount'))['amount__sum'] or 0

    return (bank_transfer_count, bank_transfer_amount)


def get_debit_cards(start_of_month, end_of_month):
    queryset_debit_card = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_month, end_of_month))
    debit_card_amount = queryset_debit_card.aggregate(Sum('amount'))['amount__sum'] or 0
    debit_card_count = queryset_debit_card.count()

    return (debit_card_amount, debit_card_count)


def make_first_of_month(month, month_year, tz):
    month_and_year = datetime.datetime(year=month_year, month=month, day=1)
    month_and_year = tz.localize(month_and_year)

    return month_and_year


def get_percentage_errors(start_of_current_month, start_of_next_month, start_of_current_month_last_year, start_of_next_month_last_year):
    queryset_debit_card_current_month = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_current_month, start_of_next_month))
    queryset_debit_card_current_month_last_year = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_current_month_last_year, start_of_next_month_last_year))
    total_credit_this_month = queryset_debit_card_current_month.exclude(resolution=CREDIT_RESOLUTION.INITIAL)
    error_credit_this_month = total_credit_this_month.filter(transaction__isnull=False)
    total_credit_this_month_last_year = queryset_debit_card_current_month_last_year.exclude(resolution=CREDIT_RESOLUTION.INITIAL)
    error_credit_last_year = total_credit_this_month_last_year.filter(transaction__isnull=False)

    percent_of_errors_this_month = error_percentage(error_credit_this_month.count(), total_credit_this_month.count())
    percent_of_errors_this_month_last_year = error_percentage(error_credit_last_year.count(), total_credit_this_month_last_year.count())

    return (percent_of_errors_this_month, percent_of_errors_this_month_last_year)


class DashboardView(TemplateView):
    """
    Django admin view which presents an overview report for MTP
    """
    template_name = 'the_dashboard/the_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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

        formated_date_previous_month_and_current_year = '{:%B %Y}'.format(start_of_previous_month)
        formated_date_current_month_and_year = '{:%B %Y}'.format(start_of_current_month)
        formated_date_current_month_last_year = '{:%B %Y}'.format(start_of_current_month_last_year)
        percent_of_errors_this_month, percent_of_errors_this_month_last_year = get_percentage_errors(start_of_current_month, start_of_next_month, start_of_current_month_last_year, start_of_next_month_last_year)

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
        context['formated_previous_month_and_current_year'] = formated_date_previous_month_and_current_year
        context['formated_current_month_and_year'] = formated_date_current_month_and_year
        context['formated_current_month_last_year'] = formated_date_current_month_last_year
        context['percent_of_errors_last_month'] = percent_of_errors_this_month
        context['percent_of_errors_last_month_last_year'] = percent_of_errors_this_month_last_year

        context['data'] = self.get_monthly_data(month, year)
        context['savings_made'] = self.get_savings(start_of_current_year, today, digital_transactions_count_this_year, queryset_digital_transactions_this_year)
        context['user_satisfaction'] = get_user_satisfaction()
        return context

    def get_savings(self, start_of_current_year, today, digital_transactions_count_this_year, queryset_digital_transactions_this_year):
        COST_PER_TRANSACTION_BY_POST = 5.73
        COST_PER_TRANSACTION_BY_DIGITAL = 2.22

        queryset_digital_takeup = DigitalTakeup.objects.filter(date__range=(start_of_current_year, today))
        digital_take_up_this_year = queryset_digital_takeup.mean_digital_takeup()

        transaction_by_post_this_year = transaction_by_post(digital_take_up_this_year, digital_transactions_count_this_year)
        transaction_by_digital = queryset_digital_transactions_this_year.filter(resolution=CREDIT_RESOLUTION.CREDITED).count()

        total_cost_of_transaction_by_post = transaction_by_post_this_year * COST_PER_TRANSACTION_BY_POST
        total_cost_of_transaction_by_digital = transaction_by_digital * COST_PER_TRANSACTION_BY_DIGITAL
        total_cost_if_it_was_only_by_post = (transaction_by_post_this_year + transaction_by_digital) * COST_PER_TRANSACTION_BY_POST
        actual_cost = total_cost_of_transaction_by_post + total_cost_of_transaction_by_digital
        savings_made = total_cost_if_it_was_only_by_post - actual_cost

        return round(savings_made)


    def get_monthly_data(self, month, year):
        data = []
        tz = timezone.get_current_timezone()
        start_month, start_month_year = get_next_month(month, year)

        for _ in range(5):
            next_month, next_month_year = start_month, start_month_year
            start_month, start_month_year = get_previous_month(start_month, start_month_year)
            start_of_month = make_first_of_month(start_month, start_month_year, tz)
            end_of_month = make_first_of_month(next_month, next_month_year, tz)

            transaction_by_post_by_month = get_transactions_by_post(start_of_month, end_of_month)
            debit_card_amount, debit_card_count = get_debit_cards(start_of_month, end_of_month)
            bank_transfer_count, bank_transfer_amount = get_bank_transfers(start_of_month, end_of_month)
            disbursement_bank_transfer_amount, disbursement_bank_transfer_count = get_disbursements(start_of_month, end_of_month)
            disbursement_cheque_count, disbursement_cheque_amount = get_disbursements_by_check(start_of_month, end_of_month)

            data.append({
                'start_of_month': start_of_month,
                'end_of_month': end_of_month,
                'transaction_by_post':transaction_by_post_by_month,
                'debit_card_amount': debit_card_amount,
                'debit_card_count': debit_card_count,
                'bank_transfer_count': bank_transfer_count,
                'bank_transfer_amount': bank_transfer_amount,
                'disbursement_bank_transfer_amount': disbursement_bank_transfer_amount,
                'disbursement_bank_transfer_count': disbursement_bank_transfer_count,
                'disbursement_cheque_count': disbursement_cheque_count,
                'disbursement_cheque_amount':disbursement_cheque_amount,
            })

        return data



