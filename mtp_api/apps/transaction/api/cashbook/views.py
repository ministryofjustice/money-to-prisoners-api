import django_filters

from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponseRedirect

from rest_framework import generics, filters, status as drf_status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.reverse import reverse

from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import CashbookClientIDPermissions
from prison.models import Prison

from transaction.constants import TRANSACTION_STATUS, LOCK_LIMIT
from transaction.models import Transaction

from .serializers import TransactionSerializer
from .permissions import TransactionPermissions


class StatusChoiceFilter(django_filters.ChoiceFilter):

    def filter(self, qs, value):

        if value in ([], (), {}, None, ''):
            return qs

        qs = qs.filter(**qs.model.STATUS_LOOKUP[value.lower()])
        return qs


class TransactionListFilter(django_filters.FilterSet):

    status = StatusChoiceFilter(choices=TRANSACTION_STATUS.choices)
    prison = django_filters.ModelMultipleChoiceFilter(queryset=Prison.objects.all())
    user = django_filters.ModelChoiceFilter(name='owner', queryset=User.objects.all())

    class Meta:
        model = Transaction


class TransactionViewMixin(object):

    def get_prison_set_for_user(self):
        try:
            return PrisonUserMapping.objects.get(user=self.request.user).prisons.all()
        except PrisonUserMapping.DoesNotExist:
            return Prison.objects.none()

    def get_queryset(self):
        return Transaction.objects.filter(prison__in=self.get_prison_set_for_user())


class TransactionList(TransactionViewMixin, generics.ListAPIView):
    serializer_class = TransactionSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = TransactionListFilter
    action = 'list'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        TransactionPermissions
    )


class LockTransactions(TransactionViewMixin, APIView):
    action = 'lock'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        TransactionPermissions
    )

    def post(self, request, format=None):
        with transaction.atomic():
            locked_count = self.get_queryset().locked().filter(owner=self.request.user).count()
            if locked_count < LOCK_LIMIT:
                slice_size = LOCK_LIMIT-locked_count
                to_lock = self.get_queryset().available().select_for_update()
                slice_pks = to_lock.values_list('pk', flat=True)[:slice_size]

                queryset = self.get_queryset().filter(pk__in=slice_pks)
                for t in queryset:
                    t.lock(by_user=request.user)

            redirect_url = '{url}?user={user}&status={status}'.format(
                url=reverse('cashbook:transaction-list'),
                user=request.user.pk,
                status=TRANSACTION_STATUS.LOCKED
            )
            return HttpResponseRedirect(redirect_url, status=drf_status.HTTP_303_SEE_OTHER)
