from rest_framework import mixins, viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import ActionsBasedViewPermissions
from mtp_auth.permissions import (
    CashbookClientIDPermissions, BankAdminClientIDPermissions
)
from .constants import DISBURSEMENT_RESOLUTION
from .models import Disbursement, Recipient
from .serializers import (
    DisbursementSerializer, DisbursementIdsSerializer, RecipientSerializer,
    ReadDisbursementSerializer
)


class DisbursementView(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Disbursement.objects.all().order_by('-id')
    filter_backends = (filters.DjangoFilterBackend,)
    permission_classes = (
        IsAuthenticated, ActionsBasedViewPermissions, CashbookClientIDPermissions
    )

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ReadDisbursementSerializer
        else:
            return DisbursementSerializer


class RecipientView(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Recipient.objects.all().order_by('-id')
    filter_backends = (filters.DjangoFilterBackend,)
    serializer_class = RecipientSerializer

    permission_classes = (
        IsAuthenticated, ActionsBasedViewPermissions, CashbookClientIDPermissions
    )


class ReviewDisbursementsView(APIView):
    serializer_class = DisbursementIdsSerializer
    action = 'update'
    resolution = NotImplemented
    queryset = Disbursement.objects.all()

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        ActionsBasedViewPermissions
    )

    def get_serializer(self, *args, **kwargs):
        kwargs['context'] = {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self
        }
        return self.serializer_class(*args, **kwargs)

    def post(self, request, format=None):
        deserialized = self.get_serializer(data=request.data)
        deserialized.is_valid(raise_exception=True)

        disbursement_ids = deserialized.data.get('disbursement_ids', [])
        Disbursement.objects.update_resolution(disbursement_ids, self.resolution, request.user)

        return Response(status=status.HTTP_204_NO_CONTENT)


class RejectDisbursementsView(ReviewDisbursementsView):
    resolution = DISBURSEMENT_RESOLUTION.REJECTED


class ConfirmDisbursementsView(ReviewDisbursementsView):
    resolution = DISBURSEMENT_RESOLUTION.CONFIRMED


class SendDisbursementsView(ReviewDisbursementsView):
    resolution = DISBURSEMENT_RESOLUTION.SENT

    permission_classes = (
        IsAuthenticated, ActionsBasedViewPermissions, BankAdminClientIDPermissions
    )
