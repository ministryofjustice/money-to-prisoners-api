from datetime import datetime
import logging

from django.db.transaction import atomic
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, viewsets, status, filters, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import django_filters

from core.filters import StatusChoiceFilter
from credit.models import Credit
from mtp_auth.permissions import BankAdminClientIDPermissions
from payment.models import Payment
from transaction.models import Transaction
from .constants import TRANSACTION_STATUS
from .permissions import TransactionPermissions
from .serializers import CreateTransactionSerializer, \
    UpdateRefundedTransactionSerializer, TransactionSerializer, \
    ReconcileTransactionSerializer

logger = logging.getLogger('mtp')


class TransactionListFilter(django_filters.FilterSet):
    status = StatusChoiceFilter(choices=TRANSACTION_STATUS.choices)

    class Meta:
        model = Transaction
        fields = {'received_at': ['lt', 'gte']}


class TransactionView(mixins.CreateModelMixin, mixins.UpdateModelMixin,
                      mixins.ListModelMixin, viewsets.GenericViewSet):

    filter_backends = (filters.DjangoFilterBackend, filters.OrderingFilter)
    filter_class = TransactionListFilter
    ordering_fields = ('received_at',)
    permission_classes = (
        IsAuthenticated, BankAdminClientIDPermissions,
        TransactionPermissions
    )

    def get_queryset(self):
        queryset = Transaction.objects.all()
        return queryset.select_related('credit')

    def patch_processed(self, request, *args, **kwargs):
        try:
            return self.partial_update(request, *args, **kwargs)
        except Credit.DoesNotExist as e:
            transaction_ids = sorted(e.args[0])
            logger.warning('Some transactions failed to update: [%s]' %
                           ', '.join(map(str, transaction_ids)))
            return Response(
                data={
                    'errors': [
                        {
                            'msg': 'Some transactions could not be updated',
                            'ids': transaction_ids,
                        }
                    ]
                },
                status=status.HTTP_409_CONFLICT
            )

    def get_serializer(self, *args, **kwargs):
        many = kwargs.pop('many', True)
        return super().get_serializer(many=many, *args, **kwargs)

    def get_object(self):
        """Return dummy object to allow for mass patching"""
        return Transaction()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateTransactionSerializer
        elif self.request.method == 'PATCH':
            return UpdateRefundedTransactionSerializer
        elif self.request.method == 'GET':
            if self.request.user.has_perm(
                    'transaction.view_bank_details_transaction'):
                return TransactionSerializer
            else:
                return ReconcileTransactionSerializer


class ReconcileTransactionsView(generics.GenericAPIView):
    queryset = Transaction.objects.all()
    action = 'patch_processed'
    serializer_class = TransactionSerializer

    permission_classes = (
        IsAuthenticated, BankAdminClientIDPermissions,
        TransactionPermissions
    )

    def post(self, request, format=None):
        start_date = request.data.get('received_at__gte')
        end_date = request.data.get('received_at__lt')
        if not start_date or not end_date:
            return Response(
                data={'errors': _("'received_at__gte' and 'received_at__lt' fields are required")},
                status=400
            )

        try:
            parsed_start_date = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            parsed_end_date = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d'))
        except ValueError:
            return Response(data={'errors': _("Invalid date format")},
                            status=400)

        with atomic():
            Transaction.objects.reconcile(
                parsed_start_date, parsed_end_date, request.user)
            Payment.objects.reconcile(
                parsed_start_date, parsed_end_date, request.user)
        return Response(status=204)
