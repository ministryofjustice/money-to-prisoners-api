from rest_framework import mixins, viewsets, filters
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import ActionsBasedPermissions
from mtp_auth.permissions import SendMoneyClientIDPermissions
from transaction.models import Transaction
from transaction.exceptions import InvalidStateForUpdateException
from .serializers import TransactionSerializer


class TransactionView(mixins.CreateModelMixin, mixins.UpdateModelMixin,
                      viewsets.GenericViewSet):

    queryset = Transaction.objects.all()
    filter_backends = (filters.DjangoFilterBackend,)
    permission_classes = (
        IsAuthenticated, SendMoneyClientIDPermissions,
        ActionsBasedPermissions
    )
    serializer_class = TransactionSerializer

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except InvalidStateForUpdateException as e:
            return Response(
                data={'errors': [str(e)]},
                status=http_status.HTTP_409_CONFLICT
            )
