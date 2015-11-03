from rest_framework import mixins, viewsets, status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ParseError
import django_filters

from mtp_auth.permissions import BankAdminClientIDPermissions
from transaction.models import Transaction
from .permissions import TransactionPermissions
from .serializers import CreateTransactionSerializer, \
    UpdateRefundedTransactionSerializer, TransactionSerializer, \
    ReconcileTransactionSerializer


class TransactionListFilter(django_filters.FilterSet):
    status = django_filters.MethodFilter(action='filter_status')
    file = django_filters.MethodFilter(action='filter_file')
    exclude_file_type = django_filters.MethodFilter(action='filter_exclude_file_type')

    class Meta:
        model = Transaction
        fields = ['status', 'file', 'exclude_file_type']

    def filter_file(self, queryset, value):
        return queryset.filter(file__id=value)

    def filter_exclude_file_type(self, queryset, value):
        return queryset.exclude(file__file_type_id=value)

    def filter_status(self, queryset, value):
        if value:
            values = [v.lower() for v in value.split(',')]

            if len(values) > 0:
                try:
                    status_set = queryset.filter(
                        **Transaction.STATUS_LOOKUP[values[0]])
                    for value in values[1:]:
                        status_set = status_set | queryset.filter(
                            **Transaction.STATUS_LOOKUP[value])
                    queryset = status_set
                except KeyError:
                    raise ParseError()
        return queryset


class TransactionView(mixins.CreateModelMixin, mixins.UpdateModelMixin,
                      mixins.ListModelMixin, viewsets.GenericViewSet):

    queryset = Transaction.objects.all()
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = TransactionListFilter
    permission_classes = (
        IsAuthenticated, BankAdminClientIDPermissions,
        TransactionPermissions
    )

    def patch_processed(self, request, *args, **kwargs):
        try:
            return self.partial_update(request, *args, **kwargs)
        except Transaction.DoesNotExist as e:
            return Response(
                data={
                    'errors': [
                        {
                            'msg': 'Some transactions could not be updated',
                            'ids': sorted(e.args[0])
                        }
                    ]
                },
                status=status.HTTP_409_CONFLICT
            )

    def get_serializer(self, *args, **kwargs):
        many = kwargs.pop('many', True)
        return super(TransactionView, self).get_serializer(many=many,
                                                           *args, **kwargs)

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
