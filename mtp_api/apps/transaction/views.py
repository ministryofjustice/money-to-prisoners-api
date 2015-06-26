from django.db import transaction
from django.forms import Form
from django.http import HttpResponseRedirect

from rest_framework import mixins
from rest_framework import viewsets
from rest_framework import filters
from rest_framework import status

from django_filters import FilterSet

from .models import Transaction
from mtp_auth.models import PrisonUserMapping
from prison.models import Prison
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework_extensions.bulk_operations.mixins import \
    ListUpdateModelMixin
from .serializers import TransactionSerializer, \
    CreditedOnlyTransactionSerializer


class TransactionFilterForm(Form):

    def clean_upload_counter(self):
        upload_counter = self.cleaned_data.get('upload_counter')
        if upload_counter == None:
            # get the latest if 'upload_counter' param not specified
            try:
                transaction = Transaction.objects.latest('upload_counter')
                upload_counter = transaction.upload_counter
            except Transaction.DoesNotExist:
                pass
        return upload_counter


class TransactionFilter(FilterSet):

    class Meta:
        model = Transaction
        form = TransactionFilterForm
        fields = ['upload_counter']


class OwnPrisonListModelMixin(object):

    def get_prison_set_for_user(self):
        try:
            return PrisonUserMapping.objects.get(user=self.request.user).prisons.all()
        except PrisonUserMapping.DoesNotExist:
            return Prison.objects.none()

    def get_queryset(self):
        qs = super(OwnPrisonListModelMixin, self).get_queryset()
        return qs.filter(prison__in=self.get_prison_set_for_user())


class TransactionView(
    OwnPrisonListModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet,
):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    patch_serializer_class = CreditedOnlyTransactionSerializer
    filter_backends = (
        filters.DjangoFilterBackend,
        filters.OrderingFilter,
    )
    filter_class = TransactionFilter
    ordering = ('received_at',)

    def get_queryset(self, filtering=True):
        qs = super(TransactionView, self).get_queryset()

        if not filtering:
            return qs

        if 'prison_id' in self.kwargs:
            prison_id = self.kwargs['prison_id']
            qs = qs.filter(prison_id=prison_id)

        if 'user_id' in self.kwargs:
            user_id = int(self.kwargs['user_id'])
            qs = qs.filter(owner__id=user_id)
        return qs


    def take(self, request, *args, **kwargs):
        DEFAULT_SLICE_SIZE = 20
        slice_size = int(request.query_params.get('count', DEFAULT_SLICE_SIZE))

        with transaction.atomic():
            pending = self.get_queryset(filtering=False).pending().select_for_update()
            slice_pks = pending[:slice_size].values_list('pk', flat=True)

            queryset = self.get_queryset(filtering=False).filter(pk__in=slice_pks)
            queryset.update(owner=request.user)
            return HttpResponseRedirect(reverse('transaction-prison-user-list', kwargs=kwargs), status=status.HTTP_303_SEE_OTHER)

    def release(self, request, *args, **kwargs):
        transaction_ids = request.data.get('transaction_ids', [])
        with transaction.atomic():
            self.get_queryset().filter(pk__in=transaction_ids).select_for_update().update(owner=None)

        return HttpResponseRedirect(reverse('transaction-prison-user-list', kwargs=kwargs), status=status.HTTP_303_SEE_OTHER)

    def patch(self, request, *args, **kwargs):
        """

        ---
        serializer: transaction.serializers.CreditedOnlyTransactionSerializer
        """

        # This is a bit manual :(
        deserialized = CreditedOnlyTransactionSerializer(data=request.data, many=True)
        if not deserialized.is_valid():
            return Response(deserialized.errors)

        with transaction.atomic():
            to_update = self.get_queryset().filter(pk__in=[x['id'] for x in deserialized.data]).select_for_update()
            for item in deserialized.data:
                obj = to_update.get(pk=item['id'])
                obj.credited = item['credited']
                obj.save(update_fields=['credited'])
            return Response(status=status.HTTP_204_NO_CONTENT)

