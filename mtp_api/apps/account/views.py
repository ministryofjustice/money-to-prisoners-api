from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
import django_filters
from django_filters.rest_framework import DjangoFilterBackend

from core.permissions import ActionsBasedPermissions
from .models import Balance
from .serializers import BalanceSerializer


class BalanceListFilter(django_filters.FilterSet):

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

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions
    )
