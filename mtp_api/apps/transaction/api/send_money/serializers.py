from django.db.transaction import atomic
from rest_framework import serializers

from transaction.constants import PAYMENT_OUTCOME
from transaction.models import Transaction
from transaction.signals import (
    transaction_created, transaction_prisons_need_updating,
    transaction_payment_taken, transaction_payment_failed
)
from transaction.exceptions import InvalidStateForUpdateException


class TransactionSerializer(serializers.ModelSerializer):

    @atomic
    def create(self, validated_data):
        transaction = super().create(validated_data)
        user = self.context['request'].user

        transaction_created.send(
            sender=Transaction,
            transaction=transaction,
            by_user=user
        )
        transaction_prisons_need_updating.send(sender=Transaction)
        return transaction

    @atomic
    def update(self, instance, validated_data):
        # only allow update of outcome field
        cleaned_data = {
            'payment_outcome': validated_data['payment_outcome']
        }
        if instance.payment_outcome != PAYMENT_OUTCOME.PENDING:
            raise InvalidStateForUpdateException(
                '"payment_outcome" cannot be updated from %s to %s'
                % (instance.payment_outcome, validated_data['payment_outcome'])
            )

        transaction = super().update(instance, cleaned_data)
        user = self.context['request'].user

        if transaction.payment_outcome == PAYMENT_OUTCOME.TAKEN:
            transaction_payment_taken.send(
                sender=Transaction,
                transaction=transaction,
                by_user=user
            )
        elif transaction.payment_outcome == PAYMENT_OUTCOME.FAILED:
            transaction_payment_failed.send(
                sender=Transaction,
                transaction=transaction,
                by_user=user
            )
        return transaction

    class Meta:
        model = Transaction
        read_only_fields = ('id',)
        fields = (
            'id',
            'prisoner_number',
            'prisoner_dob',
            'reference',
            'amount',
            'received_at',
            'category',
            'payment_outcome'
        )
