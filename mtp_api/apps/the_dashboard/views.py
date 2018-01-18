import datetime

from django.shortcuts import render

from django.http import HttpResponse
from transaction.models import Transaction, TRANSACTION_CATEGORY, TRANSACTION_SOURCE, TRANSACTION_STATUS
from django.views.generic import FormView, TemplateView
from django.utils import timezone
from credit.models import Credit
from payment.models import Payment

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
            queryset_transaction = Transaction.objects.filter(received_at__range=(timezone.now() - datetime.timedelta(days = 30 * (month + 1)), timezone.now() - datetime.timedelta(days = 30 * month)))

            queryset_credit = Credit.objects.filter(received_at__range=(timezone.now() - datetime.timedelta(days = 30 * (month + 1)), timezone.now() - datetime.timedelta(days = 30 * month)))

            # queryset_credit_amount = Credit.objects.filter(received_at__range=(timezone.now() - datetime.timedelta(days = 30 * (month + 1)), timezone.now() - datetime.timedelta(days = 30 * month)))

            data.append({
            'transaction_count': queryset_transaction.count(),
            'credit_count': queryset_credit.count(),
            # 'queryset_credit_amount': queryset_credit_amount
            })

        return context


