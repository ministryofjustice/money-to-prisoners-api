import django_filters

from django.contrib.auth.models import User

from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated

from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import CashbookClientIDPermissions
from prison.models import Prison

from transaction.constants import TRANSACTION_STATUS
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


class TransactionList(generics.ListAPIView):
    serializer_class = TransactionSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = TransactionListFilter
    action = 'list'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        TransactionPermissions
    )

    def get_prison_set_for_user(self):
        try:
            return PrisonUserMapping.objects.get(user=self.request.user).prisons.all()
        except PrisonUserMapping.DoesNotExist:
            return Prison.objects.none()

    def get_queryset(self):
        return Transaction.objects.filter(prison__in=self.get_prison_set_for_user())
