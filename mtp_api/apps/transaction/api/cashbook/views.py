import django_filters

from django.db import transaction
from django.http import HttpResponseRedirect

from rest_framework import mixins, viewsets, filters, status, exceptions
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse

from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import CashbookClientIDPermissions
from prison.models import Prison

from transaction.models import Transaction
from transaction.constants import TRANSACTION_STATUS, LOCK_LIMIT, \
    DEFAULT_SLICE_SIZE

from .serializers import TransactionSerializer, \
    CreditedOnlyTransactionSerializer
from .permissions import IsOwner, IsOwnPrison, TransactionPermissions


class StatusChoiceFilter(django_filters.ChoiceFilter):

    def filter(self, qs, value):

        if value in ([], (), {}, None, ''):
            return qs

        qs = qs.filter(**qs.model.STATUS_LOOKUP[value.lower()])
        return qs


class TransactionStatusFilter(django_filters.FilterSet):

    status = StatusChoiceFilter(choices=TRANSACTION_STATUS.choices)

    class Meta:
        model = Transaction
        fields = ['status']


class OwnPrisonListModelMixin(object):

    def get_prison_set_for_user(self):
        try:
            return PrisonUserMapping.objects.get(user=self.request.user).prisons.all()
        except PrisonUserMapping.DoesNotExist:
            return Prison.objects.none()

    def get_queryset(self):
        qs = super(OwnPrisonListModelMixin, self).get_queryset()
        return qs.filter(prison__in=self.get_prison_set_for_user())


class TransactionView(
    OwnPrisonListModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet,
):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    patch_serializer_class = CreditedOnlyTransactionSerializer
    filter_backends = (
        filters.DjangoFilterBackend,
        filters.OrderingFilter,
    )

    filter_class = TransactionStatusFilter

    ordering = ('received_at',)
    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        IsOwnPrison, TransactionPermissions
    )

    def get_queryset(self, filter_by_user=True, filter_by_prison=True):
        qs = super(TransactionView, self).get_queryset()

        prison_id = self.kwargs.get('prison_id')
        user_id = self.kwargs.get('user_id')

        if prison_id and filter_by_prison:
            qs = qs.filter(prison_id=prison_id)

        if user_id and filter_by_user:
            qs = qs.filter(owner__id=user_id)

        return qs

    def lock(self, request, *args, **kwargs):
        self.permission_classes = list(self.permission_classes) + [IsOwner]
        self.check_permissions(request)

        slice_size = self.get_slice_limit(request)

        with transaction.atomic():
            locked = self.get_queryset(filter_by_user=False).available().select_for_update()
            slice_pks = locked.values_list('pk', flat=True)[:slice_size]

            queryset = self.get_queryset(filter_by_user=False).filter(pk__in=slice_pks)
            for t in queryset:
                t.lock(by_user=request.user)

            return HttpResponseRedirect(
                reverse('cashbook:transaction-prison-user-list', kwargs=kwargs),
                status=status.HTTP_303_SEE_OTHER
            )

    def get_slice_limit(self, request):
        slice_size = int(request.query_params.get('count', DEFAULT_SLICE_SIZE))
        available_to_lock = max(0, LOCK_LIMIT - self.queryset.locked().filter(owner=request.user).count())
        if available_to_lock < slice_size:
            raise exceptions.ParseError(detail='Can\'t lock more than %s transactions.' % LOCK_LIMIT)

        return slice_size

    def unlock(self, request, *args, **kwargs):

        transaction_ids = request.data.get('transaction_ids', [])
        with transaction.atomic():
            to_update = self.get_queryset().locked().filter(pk__in=transaction_ids).select_for_update()
            if len(to_update) != len(transaction_ids):
                return Response(
                    data={'transaction_ids': ['Some transactions could not be unlocked.']},
                    status=status.HTTP_400_BAD_REQUEST
                )
            for t in to_update:
                t.unlock(by_user=request.user)

        return HttpResponseRedirect(
            reverse('cashbook:transaction-prison-user-list', kwargs=kwargs),
            status=status.HTTP_303_SEE_OTHER
        )

    def patch_credited(self, request, *args, **kwargs):
        """
        Update the credited/not credited status of list of owned transactions

        ---
        serializer: transaction.serializers.CreditedOnlyTransactionSerializer
        """
        self.permission_classes = list(self.permission_classes) + [IsOwner]
        self.check_permissions(request)

        # This is a bit manual :(
        deserialized = CreditedOnlyTransactionSerializer(data=request.data, many=True)
        if not deserialized.is_valid():
            return Response(
                deserialized.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            try:
                to_update = self.get_queryset().filter(
                    owner=request.user,
                    pk__in=[x['id'] for x in deserialized.data]
                ).select_for_update()

                for item in deserialized.data:
                    obj = to_update.get(pk=item['id'])

                    obj.credit(credited=item['credited'], by_user=request.user)
                return Response(status=status.HTTP_204_NO_CONTENT)
            except Transaction.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)
