import datetime

from django.shortcuts import render

from django.http import HttpResponse
from transaction.models import Transaction, TRANSACTION_CATEGORY, TRANSACTION_SOURCE, TRANSACTION_STATUS
from django.views.generic import FormView, TemplateView
from django.utils import timezone
from credit.models import Credit
from payment.models import Payment
from django.db.models import Sum
import pytz

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

        for _ in range(6):
            #start_of_month = timezone.now() - datetime.timedelta(days = 30 * (month + 1))
            #end_of_month = timezone.now() - datetime.timedelta(days = 30 * month)

            end_of_month = datetime.datetime(year=year, month=month, day=1)
            month -= 1
            if month == 0:
                month = 12
                year -= 1
            start_of_month = datetime.datetime(year=year, month=month, day=1)
            start_of_month = tz.localize(start_of_month)
            end_of_month = tz.localize(end_of_month)

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

            def as_a_percentage(credit, transaction):
                if(credit == None):
                     credit = 0
                if(transaction == None):
                    transaction = 0
                if(credit == 0 and transaction == 0):
                    percent = {'percent_of_credit': 0, 'percent_of_transaction': 0}
                else:
                    total = credit + transaction
                    percent_of_credit = credit/total * 100
                    percent_of_transaction = transaction/total * 100
                    percent = {'percent_of_credit': round(percent_of_credit, 2), 'percent_of_transaction': round(percent_of_transaction, 2)}
                return percent

            percent_of_use = as_a_percentage(queryset_credit.count(), queryset_transaction.count())
            percent_of_amount = as_a_percentage(queryset_credit_amount['amount__sum'], queryset_transaction_amount['amount__sum'])

            data.append({
            'transaction_count': queryset_transaction.count(),
            'credit_count': queryset_credit.count(),
            'queryset_credit_amount': amount_credit_to_pounds,
            'queryset_transaction_amount': amount_transaction_to_pounds,
            'percent_of_credit_count': percent_of_use['percent_of_credit'],
            'percent_of_transaction_count': percent_of_use['percent_of_transaction'],
            'percent_credit_amount': percent_of_amount['percent_of_credit'],
            'percent_transaction_amount': percent_of_amount['percent_of_transaction'],
            'start_of_month': start_of_month,
            'end_of_month': end_of_month
            })

        return context




