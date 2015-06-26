import uuid
from django.http import HttpResponseRedirect
from django.db import transaction

from rest_framework import viewsets
from accounting.models import Log

from rest_framework.decorators import list_route, detail_route
from rest_framework.response import Response
from rest_framework import status

from transaction.models import Transaction
from accounting.serializers import NewBatchSerializer, \
    AccountingBatchSerializer


class AccountingBatchView(viewsets.GenericViewSet):
    """
    ViewSet to start / commit / discard batch of work
    """

    queryset = Log.objects.all()
    serializer_class = NewBatchSerializer

    def get_queryset(self):
        return self.queryset.locked_by(self.request.user)


    def existing_batch_exists(self):
        if self.get_queryset().exists():
            return self.get_queryset().first().batch_reference


    def retrieve(self, request, pk=None):
        """
        See your current batch, 404 if not current batch exists
        """

        batch_objs = AccountingBatch.objects.batch(pk).locked_by(request.user)

        if not batch_objs.exists():
            return Response(status=status.HTTP_404_NOT_FOUND)

        batch_reference = batch_objs.first().batch_reference

        locked_by = request.user.id
        serialized = NewBatchSerializer(
            data={
                "transactions": AccountingBatchSerializer(batch_objs, many=True).data,
                "locked_by": locked_by,
                "batch_reference": batch_reference,
            }
        )
        if not serialized.is_valid():
            return Response(serialized.errors)

        return Response(serialized.data)

    @list_route(methods=['POST'])
    def start(self, request, format=None):
        """
        Start a new batch of work, if a batch
        already exists for the user then they
        are redirected to their current batch

        ---
        responseMessages:
          -  code: 409
             message: Conflict - there is already an existing batch for this user.

        """

        existing_batch = self.existing_batch_exists()
        if existing_batch:
            return Response({
                'batch_reference': existing_batch,
                'message': 'Batch already exists.'
            }, status=status.HTTP_409_CONFLICT)

        pending_transactions = Transaction.objects.pending().values_list('pk', flat=True)[0:20]
        batch_reference = uuid.uuid4()
        locked_by = request.user.id

        batch = []
        for t_id in pending_transactions:
            batch.append(
                AccountingBatch(batch_reference=batch_reference,
                                locked_by_id=locked_by,
                                transaction_id=t_id)
            )
        batch_objs = AccountingBatch.objects.bulk_create(batch)
        serialized = NewBatchSerializer(
            data=
            {
                "transactions": AccountingBatchSerializer(batch_objs, many=True).data,
                "locked_by": locked_by,
                "batch_reference": batch_reference,
            })

        if not serialized.is_valid():
            return Response(serialized.errors)

        return Response(serialized.data)

    @detail_route(methods=['PUT'])
    def credit(self, request, pk=None):
        """
        PUT to this endpoint with a list
        of transaction_ids to indicate that
        that have been credited in NOMS
        """
        transaction_ids = request.DATA.get('transaction_ids')
        with transaction.atomic():
            batch = AccountingBatch.objects.locked_by(request.user).batch(pk)

            if not batch.exists():
                return Response(status=status.HTTP_404_NOT_FOUND)

            batch.select_for_update()
            batch_to_credit = batch.filter(transaction_id__in=transaction_ids)

            if not batch_to_credit.count():
                return Response(status=status.HTTP_404_NOT_FOUND)

            batch_to_credit.update(credited=True)
            return Response(
                {
                    'credited':
                        batch_to_credit.values_list('transaction__id', flat=True)
                }, status=status.HTTP_200_OK
            )


    @detail_route(methods=['PUT'])
    def unlock(self, request, pk=None):
        """
        Unlock a locked batch, if `batch_reference`
        is not supplied in the parameters then
        the one for the current user is implied.
        However any user can unlock any batch if
        they need to.
        """
        batch = AccountingBatch.objects\
            .locked_by(request.user)\
            .batch(pk)

        if not batch.exists():
            Response(status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            batch.select_for_update().update(discarded=True)
            return Response(status=status.HTTP_204_NO_CONTENT)
