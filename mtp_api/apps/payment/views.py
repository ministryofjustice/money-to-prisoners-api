import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from rest_framework import mixins, viewsets
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.filters import IsoDateTimeFilter
from core.views import AdminViewMixin
from mtp_auth.permissions import (
    BankAdminClientIDPermissions, SendMoneyClientIDPermissions,
)
from payment.constants import PAYMENT_STATUS
from payment.exceptions import InvalidStateForUpdateException
from payment.forms import PaymentSearchForm
from payment.models import Batch, Payment
from payment.permissions import BatchPermissions, PaymentPermissions
from payment.serializers import BatchSerializer, PaymentSerializer


class BatchListFilter(django_filters.FilterSet):
    class Meta:
        model = Batch
        fields = ('date',)


class BatchView(
    mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    filter_backends = (DjangoFilterBackend,)
    filter_class = BatchListFilter

    permission_classes = (
        IsAuthenticated, BatchPermissions, BankAdminClientIDPermissions
    )


class PaymentListFilter(django_filters.FilterSet):
    modified__lt = IsoDateTimeFilter(
        field_name='modified', lookup_expr='lt'
    )

    class Meta:
        model = Payment
        fields = ('modified__lt',)


class PaymentView(
    mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    filter_backends = (DjangoFilterBackend,)
    filter_class = PaymentListFilter

    permission_classes = (
        IsAuthenticated, PaymentPermissions, SendMoneyClientIDPermissions
    )

    def get_queryset(self):
        return self.queryset.select_related('credit')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(status=PAYMENT_STATUS.PENDING)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except InvalidStateForUpdateException as e:
            return Response(
                data={'errors': [str(e)]},
                status=http_status.HTTP_409_CONFLICT
            )


class PaymentSearchView(AdminViewMixin, FormView):
    title = _('Payment search')
    form_class = PaymentSearchForm
    template_name = 'admin/payment/payment/search.html'
    success_url = reverse_lazy('admin:payment_search')
    superuser_required = True

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['opts'] = Payment._meta
        return context_data

    def form_valid(self, form):
        return self.render_to_response(self.get_context_data(form=form))
