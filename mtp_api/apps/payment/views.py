import django_filters
from rest_framework import mixins, viewsets, filters
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.filters import IsoDateTimeFilter
from mtp_auth.permissions import (
    BankAdminClientIDPermissions, SendMoneyClientIDPermissions
)
from .constants import PAYMENT_STATUS
from .exceptions import InvalidStateForUpdateException
from .models import Batch, Payment
from .permissions import BatchPermissions, PaymentPermissions
from .serializers import BatchSerializer, PaymentSerializer


class BatchListFilter(django_filters.FilterSet):

    class Meta:
        model = Batch
        fields = ('date',)


class BatchView(
    mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = BatchListFilter

    permission_classes = (
        IsAuthenticated, BatchPermissions, BankAdminClientIDPermissions
    )


class PaymentListFilter(django_filters.FilterSet):
    modified__lt = IsoDateTimeFilter(
        name='modified', lookup_expr='lt'
    )

    class Meta:
        model = Payment


class PaymentView(
    mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = PaymentListFilter

    permission_classes = (
        IsAuthenticated, PaymentPermissions, SendMoneyClientIDPermissions
    )

    def get_queryset(self):
        return self.queryset.select_related('credit')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(status=PAYMENT_STATUS.PENDING)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except InvalidStateForUpdateException as e:
            return Response(
                data={'errors': [str(e)]},
                status=http_status.HTTP_409_CONFLICT
            )
