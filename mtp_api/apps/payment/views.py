from django.http import Http404
import django_filters
from rest_framework import mixins, viewsets, filters
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mtp_auth.permissions import (
    BankAdminClientIDPermissions, SendMoneyClientIDPermissions
)
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


class PaymentView(
    mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

    permission_classes = (
        IsAuthenticated, PaymentPermissions, SendMoneyClientIDPermissions
    )

    def get_queryset(self):
        queryset = Payment.objects.all()
        return queryset.select_related('credit')

    def list(self, request, *args, **kwargs):
        raise Http404

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except InvalidStateForUpdateException as e:
            return Response(
                data={'errors': [str(e)]},
                status=http_status.HTTP_409_CONFLICT
            )
