from django.db import transaction
from django.http import HttpResponseRedirect

from rest_framework import mixins, viewsets, filters, status, exceptions
import django_filters

from .models import Transaction
from mtp_auth.models import PrisonUserMapping
from prison.models import Prison
from rest_framework.response import Response
from rest_framework.reverse import reverse
from .serializers import TransactionSerializer, \
    CreditedOnlyTransactionSerializer
from transaction.constants import TRANSACTION_STATUS


class StatusChoiceFilter(django_filters.ChoiceFilter):

    def filter(self, qs, value):
        filter_lookup = {
            TRANSACTION_STATUS.PENDING:   {'owner__isnull': False, 'credited': False},
            TRANSACTION_STATUS.AVAILABLE: {'owner__isnull': True, 'credited': False},
            TRANSACTION_STATUS.CREDITED:  {'owner__isnull': False, 'credited': True}
        }

        if value in ([], (), {}, None, ''):
            return qs

        qs = qs.filter(**filter_lookup[value.lower()])
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

    def get_queryset(self, filtering=True):
        qs = super(TransactionView, self).get_queryset()

        if not filtering:
            return qs

        prison_id = self.kwargs.get('prison_id')
        user_id = self.kwargs.get('user_id')

        if prison_id:
            qs = qs.filter(prison_id=prison_id)

        if user_id:
            qs = qs.filter(owner__id=user_id)

        if not (prison_id or user_id):
            raise exceptions.NotFound()
        return qs

    def take(self, request, *args, **kwargs):
        # TODO: move to settings
        MAX_SLICE_SIZE = 20
        DEFAULT_SLICE_SIZE = 20
        slice_size = min(MAX_SLICE_SIZE, int(request.query_params.get('count', DEFAULT_SLICE_SIZE)))
        with transaction.atomic():
            pending = self.get_queryset(filtering=False).pending().select_for_update()
            slice_pks = pending[:slice_size].values_list('pk', flat=True)

            queryset = self.get_queryset(filtering=False).filter(pk__in=slice_pks)
            queryset.update(owner=request.user)
            return HttpResponseRedirect(reverse('transaction-prison-user-list', kwargs=kwargs), status=status.HTTP_303_SEE_OTHER)

    def release(self, request, *args, **kwargs):
        transaction_ids = request.data.get('transaction_ids', [])
        with transaction.atomic():
            self.get_queryset().filter(pk__in=transaction_ids).select_for_update().update(owner=None)

        return HttpResponseRedirect(reverse('transaction-prison-user-list', kwargs=kwargs), status=status.HTTP_303_SEE_OTHER)

    def patch(self, request, *args, **kwargs):
        """

        ---
        serializer: transaction.serializers.CreditedOnlyTransactionSerializer
        """
        if not request.user.id == self.kwargs['user_id']:
            raise exceptions.PermissionDenied()

        # This is a bit manual :(
        deserialized = CreditedOnlyTransactionSerializer(data=request.data, many=True)
        if not deserialized.is_valid():
            return Response(deserialized.errors)

        with transaction.atomic():
            to_update = self.get_queryset().filter(pk__in=[x['id'] for x in deserialized.data]).select_for_update()
            for item in deserialized.data:
                obj = to_update.get(pk=item['id'])
                obj.credited = item['credited']
                obj.save(update_fields=['credited'])
            return Response(status=status.HTTP_204_NO_CONTENT)

