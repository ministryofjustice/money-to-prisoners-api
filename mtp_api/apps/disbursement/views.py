from rest_framework import mixins, viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import ActionsBasedViewPermissions
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    CashbookClientIDPermissions, BankAdminClientIDPermissions,
    CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
    BANK_ADMIN_OAUTH_CLIENT_ID, get_client_permissions_class
)
from .constants import DISBURSEMENT_RESOLUTION
from .models import Disbursement, Recipient
from .serializers import (
    DisbursementSerializer, DisbursementIdsSerializer, RecipientSerializer,
    ReadDisbursementSerializer
)


class DisbursementViewMixin():
    def get_queryset(self):
        queryset = Disbursement.objects.all()
        if self.request.auth.application.client_id == CASHBOOK_OAUTH_CLIENT_ID:
            return queryset.filter(
                prison__in=PrisonUserMapping.objects.get_prison_set_for_user(self.request.user)
            )
        return queryset


class DisbursementView(
    DisbursementViewMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    queryset = Disbursement.objects.all().order_by('-id')
    filter_backends = (filters.DjangoFilterBackend,)
    permission_classes = (
        IsAuthenticated, ActionsBasedViewPermissions, get_client_permissions_class(
            CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
            BANK_ADMIN_OAUTH_CLIENT_ID
        )
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
        IsAuthenticated, ActionsBasedViewPermissions, get_client_permissions_class(
            CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
            BANK_ADMIN_OAUTH_CLIENT_ID
        )
    )


class ReviewDisbursementsView(DisbursementViewMixin, APIView):
    serializer_class = DisbursementIdsSerializer
    action = 'update'
    resolution = NotImplemented

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
        Disbursement.objects.update_resolution(
            self.get_queryset(), disbursement_ids, self.resolution, request.user
        )

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
