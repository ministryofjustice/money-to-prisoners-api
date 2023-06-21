from django.db import transaction as db_transaction

from rest_framework import serializers, fields

from credit.models import Credit
from credit.signals import credit_created
from payment.models import Batch
from prison.serializers import PrisonSerializer
from transaction.constants import TransactionCategory, TransactionSource
from transaction.models import Transaction


class CreateTransactionListSerializer(serializers.ListSerializer):
    @db_transaction.atomic
    def create(self, validated_data):
        transactions = []
        user = self.context['request'].user

        for data in validated_data:
            batch = data.pop('batch', None)
            prisoner_number = data.pop('prisoner_number', None)
            prisoner_dob = data.pop('prisoner_dob', None)
            blocked = data.pop('blocked', False)
            if (data['category'] == TransactionCategory.credit.value and
                    data['source'] == TransactionSource.bank_transfer.value):
                new_credit = Credit(
                    amount=data['amount'],
                    prisoner_number=prisoner_number,
                    prisoner_dob=prisoner_dob,
                    received_at=data['received_at'],
                    blocked=blocked
                )
                new_credit.save()
                data['credit'] = new_credit

                credit_created.send(
                    sender=Credit,
                    credit=new_credit,
                    by_user=user,
                )

            transaction = Transaction.objects.create(**data)
            if batch:
                batch.settlement_transaction = transaction
                batch.save()
            transactions.append(transaction)

        return transactions


class CreateTransactionSerializer(serializers.ModelSerializer):
    prisoner_dob = serializers.DateField(required=False)
    prisoner_number = serializers.CharField(required=False)
    blocked = serializers.BooleanField(required=False)
    batch = serializers.PrimaryKeyRelatedField(queryset=Batch.objects.all(), required=False)

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
            'received_at',
            'category',
            'ref_code',
            'source',
            'incomplete_sender_info',
            'processor_type_code',
            'reference_in_sender_field',
            'batch',
            'blocked',
        )


class UpdateTransactionListSerializer(serializers.ListSerializer):
    def update(self, instance, validated_data):
        user = self.context['request'].user

        to_refund = [t['id'] for t in validated_data if t['refunded']]

        updated_transactions = []
        if to_refund:
            Credit.objects.refund(to_refund, user)
            updated_transactions = Transaction.objects.filter(pk__in=to_refund)

        return updated_transactions


class UpdateRefundedTransactionSerializer(serializers.ModelSerializer):
    id = fields.IntegerField(required=True)
    refunded = fields.BooleanField(required=True)

    class Meta:
        model = Transaction
        list_serializer_class = UpdateTransactionListSerializer
        fields = (
            'id',
            'refunded',
        )


class TransactionSerializer(serializers.ModelSerializer):
    prison = PrisonSerializer(required=False)
    credited = fields.BooleanField()
    refunded = fields.BooleanField()
    blocked = fields.BooleanField()

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
            'refunded',
            'received_at',
            'category',
            'source',
            'ref_code',
            'reference_in_sender_field',
            'blocked',
        )


class ReconcileTransactionSerializer(serializers.ModelSerializer):
    prison = PrisonSerializer(required=False)
    credited = fields.BooleanField()
    refunded = fields.BooleanField()

    class Meta:
        model = Transaction
        fields = (
            'id',
            'prison',
            'amount',
            'credited',
            'refunded',
            'received_at',
            'category',
            'source',
            'ref_code',
        )
