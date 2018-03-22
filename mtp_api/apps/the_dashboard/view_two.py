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
from disbursement.constants import DISBURSEMENT_METHOD


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


def get_disbursements_by_check(start_of_month, end_of_month):
    queryset_disbursement_cheque = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.CHEQUE).filter(created__range=(start_of_month, end_of_month))
    disbursement_cheque_count = queryset_disbursement_cheque.count()

    return disbursement_cheque_count


def get_disbursements(start_of_month, end_of_month):
    queryset_disbursement_bank_transfer = Disbursement.objects.filter(method=DISBURSEMENT_METHOD.BANK_TRANSFER).filter(created__range=(start_of_month, end_of_month))
    disbursement_bank_transfer_count = queryset_disbursement_bank_transfer.count()

    return disbursement_bank_transfer_count


def get_bank_transfers(start_of_month, end_of_month):
    queryset_bank_transfer = Credit.objects.filter(transaction__isnull=False).filter(received_at__range=(start_of_month, end_of_month))
    bank_transfer_count = queryset_bank_transfer.count()

    return bank_transfer_count


def get_debit_cards(start_of_month, end_of_month):
    queryset_debit_card = Credit.objects.filter(payment__isnull=False).filter(received_at__range=(start_of_month, end_of_month))
    debit_card_count = queryset_debit_card.count()

    return debit_card_count


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

    return round(transaction_by_post_by_month)


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
        next_year = year + 1
        last_month, last_months_year = get_previous_month(month, year)
        next_month, next_months_year = get_next_month(month, year)

        start_of_last_year = today.replace(month=1, year=last_year, day=1)
        start_of_previous_month = today.replace(month=last_month, year=last_months_year, day=1)
        start_of_current_month = today.replace(month=month, year=year, day=1)
        start_of_next_month = today.replace(month=next_month, year=next_months_year, day=1)
        start_of_current_year = today.replace(month=1, day=1)


        if month > 4 and year:
            start_of_financial_year = today.replace(month=4, year=year, day=1)
        else:
            start_of_financial_year = today.replace(month=4, year=last_year, day=1)


        if month > 4 and year:
            end_of_financial_year = today.replace(month=4, year=next_year, day=30)
        else:
            end_of_financial_year = today.replace(month=4, year=year, day=30)

        queryset_digital_transactions_previous_week = Credit.objects.filter(received_at__range=(start_of_previous_week,  end_of_previous_week))
        queryset_digital_transactions_week_so_far = Credit.objects.filter(received_at__range=(end_of_previous_week, today))
        queryset_digital_transactions_previous_month = Credit.objects.filter(received_at__range=(start_of_previous_month, start_of_current_month))
        queryset_digital_transactions_this_month = Credit.objects.filter(received_at__range=(start_of_current_month, start_of_next_month))
        queryset_digital_transactions_previous_year = Credit.objects.filter(received_at__range=(start_of_last_year, start_of_current_year))
        queryset_digital_transactions_this_year = Credit.objects.filter(received_at__range=(start_of_current_year, today))
        queryset_digital_transactions_this_financial_year = Credit.objects.filter(received_at__range=(start_of_financial_year, end_of_financial_year))


        queryset_disbursement_previous_week = Disbursement.objects.filter(created__range=(start_of_previous_week, end_of_previous_week))
        queryset_disbursement_week_so_far = Disbursement.objects.filter(created__range=(end_of_previous_week, today))
        queryset_disbursement_previous_month = Disbursement.objects.filter(created__range=(start_of_previous_month, start_of_current_month))
        queryset_disbursement_this_month = Disbursement.objects.filter(created__range=(start_of_current_month, start_of_next_month))
        queryset_disbursements_previous_year = Disbursement.objects.filter(created__range=(start_of_last_year, start_of_current_year))
        queryset_disbursements_this_year = Disbursement.objects.filter(created__range=(start_of_current_year, today))

        disbursement_count_previous_week = queryset_disbursement_previous_week.count()
        disbursement_amount_previous_week = queryset_disbursement_previous_week.aggregate(Sum('amount'))['amount__sum']
        disbursement_count_week_so_far = queryset_disbursement_week_so_far.count()
        disbursement_amount_week_so_far = queryset_disbursement_week_so_far.aggregate(Sum('amount'))['amount__sum']
        disbursement_count_previous_month = queryset_disbursement_previous_month.count()
        disbursement_amount_previous_month = queryset_disbursement_previous_month.aggregate(Sum('amount'))['amount__sum'] or 0
        disbursement_count_this_month = queryset_disbursement_this_month.count()
        disbursement_amount_this_month = queryset_disbursement_this_month.aggregate(Sum('amount'))['amount__sum'] or 0
        disbursement_count_previous_year = queryset_disbursements_previous_year.count()
        disbursement_amount_previous_year = queryset_disbursements_previous_year.aggregate(Sum('amount'))['amount__sum']
        disbursement_count_this_year = queryset_disbursements_this_year.count()
        disbursement_amount_this_year = queryset_disbursements_this_year.aggregate(Sum('amount'))['amount__sum']

        digital_transactions_amount_previous_week = queryset_digital_transactions_previous_week.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_previous_week = queryset_digital_transactions_previous_week.count()
        digital_transactions_amount_week_so_far = queryset_digital_transactions_week_so_far.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_week_so_far = queryset_digital_transactions_week_so_far.count()
        digital_transactions_count_previous_month = queryset_digital_transactions_previous_month.count()
        digital_transactions_amount_previous_month = queryset_digital_transactions_previous_month.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_this_month = queryset_digital_transactions_this_month.count()
        digital_transactions_amount_this_month = queryset_digital_transactions_this_month.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_previous_year = queryset_digital_transactions_previous_year.count()
        digital_transactions_amount_previous_year = queryset_digital_transactions_previous_year.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_this_year = queryset_digital_transactions_this_year.count()
        digital_transactions_amount_this_year = queryset_digital_transactions_this_year.aggregate(Sum('amount'))['amount__sum']
        digital_transactions_count_this_financial_year = queryset_digital_transactions_this_financial_year.count()



        context['disbursement_count_previous_week']= disbursement_count_previous_week
        context['disbursement_amount_previous_week'] = disbursement_amount_previous_week
        context['disbursement_count_week_so_far'] = disbursement_count_week_so_far
        context['disbursement_amount_week_so_far']= disbursement_amount_week_so_far
        context['disbursement_count_last_month'] = disbursement_count_previous_month
        context['disbursement_amount_last_month'] = disbursement_amount_previous_month
        context['disbursement_count_this_month'] = disbursement_count_this_month
        context['disbursement_amount_this_month'] = disbursement_amount_this_month
        context['disbursement_count_previous_year'] = disbursement_count_previous_year
        context['disbursement_amount_previous_year'] = disbursement_amount_previous_year
        context['disbursement_count_this_year']= disbursement_count_this_year
        context['disbursement_amount_this_year'] = disbursement_amount_this_year

        context['digital_transactions_amount_previous_week'] = digital_transactions_amount_previous_week
        context['digital_transactions_count_previous_week']= digital_transactions_count_previous_week
        context['digital_transactions_amount_week_so_far'] = digital_transactions_amount_week_so_far
        context['digital_transactions_count_week_so_far'] = digital_transactions_count_week_so_far
        context['digital_transactions_count_previous_month'] = digital_transactions_count_previous_month
        context['digital_transactions_amount_previous_month'] = digital_transactions_amount_previous_month
        context['digital_transactions_count_this_month'] = digital_transactions_count_this_month
        context['digital_transactions_amount_this_month'] = digital_transactions_amount_this_month
        context['digital_transactions_count_previous_year'] = digital_transactions_count_previous_year
        context['digital_transactions_amount_previous_year'] = digital_transactions_amount_previous_year
        context['digital_transactions_count_this_year'] = digital_transactions_count_this_year
        context['digital_transactions_amount_this_year'] =  digital_transactions_amount_this_year

        context['data'] = self.get_monthly_data(month, year)
        context['savings'] =  self.get_savings(start_of_financial_year, end_of_financial_year, digital_transactions_count_this_financial_year, queryset_digital_transactions_this_financial_year)
        context['user_satisfaction'] = get_user_satisfaction()
        return context

    def get_savings(self, start_of_financial_year, end_of_financial_year, digital_transactions_count_this_financial_year, queryset_digital_transactions_this_financial_year):
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


    def get_monthly_data(self, month, year):
        data = []
        tz = timezone.get_current_timezone()
        start_month, start_month_year = get_next_month(month, year)

        for _ in range(6):
            next_month, next_month_year = start_month, start_month_year
            start_month, start_month_year = get_previous_month(start_month, start_month_year)
            start_of_month = make_first_of_month(start_month, start_month_year, tz)
            end_of_month = make_first_of_month(next_month, next_month_year, tz)

            transaction_by_post_by_month = get_transactions_by_post(start_of_month, end_of_month)
            debit_card_count = get_debit_cards(start_of_month, end_of_month)
            bank_transfer_count = get_bank_transfers(start_of_month, end_of_month)
            disbursement_bank_transfer_count = get_disbursements(start_of_month, end_of_month)
            disbursement_cheque_count = get_disbursements_by_check(start_of_month, end_of_month)

            data.append({
                'start_of_month': start_of_month,
                'end_of_month': end_of_month,
                'transaction_by_post':transaction_by_post_by_month,
                'debit_card_count': debit_card_count,
                'bank_transfer_count': bank_transfer_count,
                'disbursement_bank_transfer_count': disbursement_bank_transfer_count,
                'disbursement_cheque_count': disbursement_cheque_count,
            })

        return data


