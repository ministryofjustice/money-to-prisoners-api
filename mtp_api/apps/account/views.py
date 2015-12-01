from rest_framework import mixins, viewsets, filters
from rest_framework.permissions import IsAuthenticated
import django_filters

from core.permissions import ActionsBasedPermissions
from .models import Batch, Balance
from .serializers import BatchSerializer, BalanceSerializer


class BatchView(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Batch.objects.all().order_by('-created')
    serializer_class = BatchSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = ('label',)

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions
    )


class BalanceListFilter(django_filters.FilterSet):

    class Meta:
        model = Balance
        fields = {'date': ['lt', 'gte']}


class BalanceView(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Balance.objects.all().order_by('-date')
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = BalanceListFilter
    serializer_class = BalanceSerializer

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions
    )
