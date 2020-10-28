from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from account.models import Balance
from account.serializers import BalanceSerializer
from core.permissions import ActionsBasedPermissions
from core.filters import BaseFilterSet


class BalanceListFilter(BaseFilterSet):
    class Meta:
        model = Balance
        fields = {'date': ['lt', 'gte']}


class BalanceView(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Balance.objects.all().order_by('-date')
    filter_backends = (DjangoFilterBackend,)
    filter_class = BalanceListFilter
    serializer_class = BalanceSerializer

    permission_classes = (IsAuthenticated, ActionsBasedPermissions)
