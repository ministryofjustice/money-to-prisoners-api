from rest_framework import mixins, viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mtp_auth.permissions import BankAdminClientIDPermissions

from core.permissions import ActionsBasedPermissions

from transaction.models import Transaction

from .serializers import CreateTransactionSerializer


class TransactionView(
    mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = Transaction.objects.all()

    permission_classes = (
        IsAuthenticated, BankAdminClientIDPermissions,
        ActionsBasedPermissions
    )
    create_serializer_class = CreateTransactionSerializer

    def get_create_serializer(self, *args, **kwargs):
        kwargs['context'] = self.get_serializer_context()
        return self.create_serializer_class(*args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_create_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )
