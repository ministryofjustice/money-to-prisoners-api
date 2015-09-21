from django.db import transaction

from rest_framework import serializers
from rest_framework.fields import IntegerField

from transaction.signals import transaction_created, transaction_refunded, \
    transaction_prisons_need_updating
from transaction.models import Transaction
from prison.serializers import PrisonSerializer


class CreateTransactionListSerializer(serializers.ListSerializer):

    @transaction.atomic
    def create(self, validated_data):
        transactions = []
        user = self.context['request'].user

        for data in validated_data:
            transaction = Transaction.objects.create(**data)

            transaction_created.send(
                sender=Transaction,
                transaction=transaction,
                by_user=user
            )

            transactions.append(transaction)

        transaction_prisons_need_updating.send(sender=Transaction)

        return transactions


class CreateTransactionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Transaction
        list_serializer_class = CreateTransactionListSerializer
        fields = (
            'prisoner_number',
            'prisoner_dob',
            'amount',
            'sender_sort_code',
            'sender_account_number',
            'sender_name',
            'sender_roll_number',
            'reference',
            'received_at'
        )


class UpdateRefundedTransactionListSerializer(serializers.ListSerializer):

    @transaction.atomic
    def update(self, instance, validated_data):
        user = self.context['request'].user

        to_refund = [t['id'] for t in validated_data if t['refunded']]

        update_set = Transaction.objects.filter(
            pk__in=to_refund,
            **Transaction.STATUS_LOOKUP['refund_pending']).select_for_update()
        if len(update_set) != len(to_refund):
            raise Transaction.DoesNotExist(
                list(set(to_refund) - {t.id for t in update_set})
            )

        updated_transactions = list(update_set)
        update_set.update(refunded=True)

        for transaction in updated_transactions:
            transaction.refunded = True
            transaction_refunded.send(
                sender=Transaction,
                transaction=transaction,
                by_user=user
            )

        return updated_transactions


class UpdateRefundedTransactionSerializer(serializers.ModelSerializer):
    id = IntegerField(read_only=False)

    class Meta:
        model = Transaction
        list_serializer_class = UpdateRefundedTransactionListSerializer
        fields = (
            'id',
            'refunded'
        )


class TransactionSerializer(serializers.ModelSerializer):
    prison = PrisonSerializer(required=False)

    class Meta:
        model = Transaction
        fields = (
            'id',
            'prison',
            'amount',
            'sender_sort_code',
            'sender_account_number',
            'sender_name',
            'sender_roll_number',
            'reference',
            'credited',
            'refunded'
        )


class ReconcileTransactionSerializer(serializers.ModelSerializer):
    prison = PrisonSerializer(required=False)

    class Meta:
        model = Transaction
        fields = (
            'id',
            'prison',
            'amount',
            'credited',
            'refunded'
        )
