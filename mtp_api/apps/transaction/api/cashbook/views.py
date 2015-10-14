import datetime
from functools import reduce

import django_filters

from django import forms
from django.contrib.auth.models import User
from django.db import models, transaction
from django_filters.widgets import RangeWidget
from django.http import HttpResponseRedirect
from django.views.generic import View

from rest_framework import generics, filters, status as drf_status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse

from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import CashbookClientIDPermissions
from prison.models import Prison

from transaction.constants import TRANSACTION_STATUS, LOCK_LIMIT
from transaction.models import Transaction
from transaction.signals import transaction_prisons_need_updating

from .serializers import TransactionSerializer, \
    CreditedOnlyTransactionSerializer, \
    IdsTransactionSerializer
from .permissions import TransactionPermissions


class StatusChoiceFilter(django_filters.ChoiceFilter):

    def filter(self, qs, value):

        if value in ([], (), {}, None, ''):
            return qs

        qs = qs.filter(**qs.model.STATUS_LOOKUP[value.lower()])
        return qs


class DateRangeField(forms.MultiValueField):
    widget = RangeWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.DateTimeField(),
            forms.DateTimeField(),
        )
        super().__init__(fields, *args, **kwargs)

    def compress(self, data_list):
        if data_list:
            start, end = data_list
            if end:
                end += datetime.timedelta(days=1)
            return slice(start, end)
        return None


class DateRangeFilter(django_filters.RangeFilter):
    field_class = DateRangeField


class MultiFieldSearchFilter(django_filters.CharFilter):
    def __init__(self, fields, **kwargs):
        self.fields = fields
        super().__init__(**kwargs)

    def filter(self, qs, value):
        if not value:
            return qs

        def get_field_filter(field):
            return models.Q(**{'%s__icontains' % field: value})

        qs = qs.filter(
            reduce(
                lambda a, b: a | b,
                map(get_field_filter, self.fields)
            )
        )
        return qs


class TransactionListFilter(django_filters.FilterSet):

    status = StatusChoiceFilter(choices=TRANSACTION_STATUS.choices)
    prison = django_filters.ModelMultipleChoiceFilter(queryset=Prison.objects.all())
    user = django_filters.ModelChoiceFilter(name='owner', queryset=User.objects.all())
    received_at = DateRangeFilter()
    search = MultiFieldSearchFilter(fields=['prisoner_name', 'prisoner_number', 'sender_name'])

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


class GetTransactions(TransactionViewMixin, generics.ListAPIView):
    serializer_class = TransactionSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = TransactionListFilter
    action = 'list'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        TransactionPermissions
    )


class CreditTransactions(TransactionViewMixin, generics.GenericAPIView):
    serializer_class = CreditedOnlyTransactionSerializer
    action = 'patch_credited'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        TransactionPermissions
    )

    def get_serializer(self, *args, **kwargs):
        kwargs['context'] = {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self
        }
        return self.serializer_class(*args, **kwargs)

    def patch(self, request, format=None):
        deserialized = self.get_serializer(data=request.data, many=True)
        deserialized.is_valid(raise_exception=True)

        transaction_ids = [x['id'] for x in deserialized.data]
        with transaction.atomic():
            to_update = self.get_queryset().filter(
                owner=request.user,
                pk__in=transaction_ids
            ).select_for_update()

            ids_to_update = [t.id for t in to_update]
            conflict_ids = set(transaction_ids) - set(ids_to_update)

            if conflict_ids:
                return Response(
                    data={
                        'errors': [
                            {
                                'msg': 'Some transactions could not be credited.',
                                'ids': sorted(conflict_ids)
                            }
                        ]
                    },
                    status=drf_status.HTTP_409_CONFLICT
                )

            for item in deserialized.data:
                obj = to_update.get(pk=item['id'])
                obj.credit(credited=item['credited'], by_user=request.user)

        return Response(status=drf_status.HTTP_204_NO_CONTENT)


class TransactionList(View):
    """
    Dispatcher View that dispatches to GetTransactions or CreditTransactions
    depending on the method.

    The standard logic would not work in this case as:
    - the two endpoints need to do something quite different so better if
        they belong to different classes
    - we need specific permissions for the two endpoints so it's cleaner to
        use the same TransactionPermissions for all the views
    """

    def get(self, request, *args, **kwargs):
        return GetTransactions.as_view()(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return CreditTransactions.as_view()(request, *args, **kwargs)


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


class UnlockTransactions(TransactionViewMixin, APIView):
    serializer_class = IdsTransactionSerializer
    action = 'unlock'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        TransactionPermissions
    )

    def get_serializer(self, *args, **kwargs):
        kwargs['context'] = {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self
        }
        return self.serializer_class(*args, **kwargs)

    def post(self, request, format=None):
        deserialized = self.get_serializer(data=request.data)
        deserialized.is_valid(raise_exception=True)

        transaction_ids = deserialized.data.get('transaction_ids', [])
        with transaction.atomic():
            to_update = self.get_queryset().locked().filter(pk__in=transaction_ids).select_for_update()

            ids_to_update = [t.id for t in to_update]
            conflict_ids = set(transaction_ids) - set(ids_to_update)

            if conflict_ids:
                return Response(
                    data={
                        'errors': [
                            {
                                'msg': 'Some transactions could not be unlocked.',
                                'ids': sorted(conflict_ids)
                            }
                        ]
                    },
                    status=drf_status.HTTP_409_CONFLICT
                )
            for t in to_update:
                t.unlock(by_user=request.user)

        transaction_prisons_need_updating.send(sender=Transaction)

        redirect_url = '{url}?user={user}&status={status}'.format(
            url=reverse('cashbook:transaction-list'),
            user=request.user.pk,
            status=TRANSACTION_STATUS.AVAILABLE
        )
        return HttpResponseRedirect(redirect_url, status=drf_status.HTTP_303_SEE_OTHER)
