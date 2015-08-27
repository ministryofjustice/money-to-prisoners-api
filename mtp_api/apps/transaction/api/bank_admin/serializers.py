from django.db import transaction
from django.db.models import Max

from rest_framework import serializers
from rest_framework.fields import IntegerField

from transaction.signals import transaction_created, transaction_refunded
from transaction.models import Transaction


class CreateTransactionListSerializer(serializers.ListSerializer):

    @transaction.atomic
    def create(self, validated_data):
        upload_counter = Transaction.objects.all().aggregate(
            Max('upload_counter')
        )['upload_counter__max'] or 1

        transactions = []
        user = self.context['request'].user

        for data in validated_data:
            transaction = Transaction.objects.create(
                upload_counter=upload_counter, **data
            )

            transaction_created.send(
                sender=Transaction,
                transaction=transaction,
                by_user=user
            )

            transactions.append(transaction)

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
                set(to_refund) - {t.id for t in update_set}
            )

        update_set.update(refunded=True)
        for t_id in to_refund:
            transaction = Transaction()
            transaction.id = t_id
            transaction_refunded.send(
                sender=Transaction,
                transaction=transaction,
                by_user=user
            )

        return update_set


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

    class Meta:
        model = Transaction
        fields = (
            'id',
            'prison',
            'amount',
            'credited',
            'refunded'
        )
