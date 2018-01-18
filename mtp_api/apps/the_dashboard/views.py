import datetime

from django.shortcuts import render

from django.http import HttpResponse
from transaction.models import Transaction, TRANSACTION_CATEGORY, TRANSACTION_SOURCE, TRANSACTION_STATUS
from django.views.generic import FormView, TemplateView
from django.utils import timezone
from credit.models import Credit
from payment.models import Payment
from django.db.models import Sum

class DashboardView(TemplateView):
    """
    Django admin view which presents an overview report for MTP
    """
    template_name = 'the_dashboard/digital_take_up.html'




    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = []
        context['data'] = data

        for month in range(6):
            start_of_month = timezone.now() - datetime.timedelta(days = 30 * (month + 1))
            end_of_month = timezone.now() - datetime.timedelta(days = 30 * month)

            queryset_transaction = Transaction.objects.filter(received_at__range=(start_of_month, end_of_month))
            queryset_transaction_amount = Transaction.objects.filter(received_at__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))

            queryset_credit = Credit.objects.filter(received_at__range=(start_of_month, end_of_month))
            queryset_credit_amount = Credit.objects.filter(received_at__range=(start_of_month, end_of_month)).aggregate(Sum('amount'))

            def pence_to_pounds(amount):
                if(amount != None):
                    return amount/100

            amount_transaction_to_pounds = pence_to_pounds(queryset_transaction_amount['amount__sum'])
            amount_credit_to_pounds = pence_to_pounds(queryset_credit_amount['amount__sum'])

            data.append({
            'transaction_count': queryset_transaction.count(),
            'credit_count': queryset_credit.count(),
            'queryset_credit_amount': amount_credit_to_pounds,
            'queryset_transaction_amount': amount_transaction_to_pounds,
            })


            # print(data[0]['queryset_transaction_amount'])

        return context


