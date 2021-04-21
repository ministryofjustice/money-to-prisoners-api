import logging

from django.db.transaction import atomic
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets, status, generics
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.filters import (
    StatusChoiceFilter, IsoDateTimeFilter, SafeOrderingFilter,
    MultipleValueFilter, BaseFilterSet
)
from credit import InvalidCreditStateException
from credit.models import PrivateEstateBatch
from mtp_auth.permissions import BankAdminClientIDPermissions
from payment.models import Payment
from transaction.constants import TRANSACTION_STATUS
from transaction.models import Transaction
from transaction.permissions import TransactionPermissions
from transaction.serializers import (
    CreateTransactionSerializer, UpdateRefundedTransactionSerializer,
    TransactionSerializer, ReconcileTransactionSerializer
)

logger = logging.getLogger('mtp')


class TransactionListFilter(BaseFilterSet):
    status = StatusChoiceFilter(choices=TRANSACTION_STATUS.choices)
    received_at__lt = IsoDateTimeFilter(
        field_name='received_at', lookup_expr='lt'
    )
    received_at__gte = IsoDateTimeFilter(
        field_name='received_at', lookup_expr='gte'
    )
    pk = MultipleValueFilter(field_name='pk')

    class Meta:
        model = Transaction
        fields = ('status', 'received_at__lt', 'received_at__gte',)


class DjangoFilterBackendEmptyOnErrors(DjangoFilterBackend):

    def filter_queryset(self, request, queryset, view):
        filterset = self.get_filterset(request, queryset, view)
        if filterset is None:
            return queryset

        if not filterset.is_valid() and self.raise_exception:
            return filterset.qs.none()
        return filterset.qs


class TransactionView(
    mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    filter_backends = (DjangoFilterBackendEmptyOnErrors, SafeOrderingFilter)
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
        except InvalidCreditStateException as e:
            logger.warning(
                'Some transactions failed to update: %(transaction_id_list)r',
                {'transaction_id_list': e.conflict_ids}
            )
            return Response(
                data={
                    'errors': [
                        {
                            'msg': 'Some transactions could not be updated',
                            'ids': e.conflict_ids,
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
        # Having different serializers for different RESTful operations isn't
        # quite django-rest-framework best practise, so we run into problems here
        # when parsing the class with drf-yasg's OpenAPI introspection

        # For now we raise rest_framework.exceptions.APIException on this code path
        # so the introspector knows not to introspect the fields for a particular
        # given HTTP verb for this view
        if not self.request:
            raise APIException('Request not bound to view. This should only occur on introspection')
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
    actions = {'post': 'patch_processed'}

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
            parsed_start_date = parse_datetime(start_date)
            parsed_end_date = parse_datetime(end_date)
        except ValueError:
            return Response(data={'errors': _('Invalid date format')},
                            status=400)

        with atomic():
            Transaction.objects.reconcile(
                parsed_start_date, parsed_end_date, request.user)
            Payment.objects.reconcile(
                parsed_start_date, parsed_end_date, request.user)

        PrivateEstateBatch.objects.create_batches(parsed_start_date, parsed_end_date)

        return Response(status=204)
