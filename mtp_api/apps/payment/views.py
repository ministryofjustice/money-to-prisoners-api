from rest_framework import mixins, viewsets
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mtp_auth.permissions import SendMoneyClientIDPermissions
from .exceptions import InvalidStateForUpdateException
from .models import Payment
from .permissions import PaymentPermissions
from .serializers import PaymentSerializer


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

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except InvalidStateForUpdateException as e:
            return Response(
                data={'errors': [str(e)]},
                status=http_status.HTTP_409_CONFLICT
            )
