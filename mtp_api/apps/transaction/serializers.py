from django.db import transaction as db_transaction

from rest_framework import serializers, fields

from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from credit.signals import credit_refunded, credit_created
from prison.serializers import PrisonSerializer
from .constants import TRANSACTION_CATEGORY, TRANSACTION_SOURCE
from .models import Transaction


class CreateTransactionListSerializer(serializers.ListSerializer):

    @db_transaction.atomic
    def create(self, validated_data):
        transactions = []
        user = self.context['request'].user

        for data in validated_data:
            prisoner_number = data.pop('prisoner_number', None)
            prisoner_dob = data.pop('prisoner_dob', None)
            if (data['category'] == TRANSACTION_CATEGORY.CREDIT and
                    data['source'] == TRANSACTION_SOURCE.BANK_TRANSFER):
                new_credit = Credit(
                    amount=data['amount'],
                    prisoner_number=prisoner_number,
                    prisoner_dob=prisoner_dob,
                    received_at=data['received_at']
                )
                new_credit.save()
                data['credit'] = new_credit

                credit_created.send(
                    sender=Credit,
                    credit=new_credit,
                    by_user=user
                )

            transaction = Transaction.objects.create(**data)
            transactions.append(transaction)

        return transactions


class CreateTransactionSerializer(serializers.ModelSerializer):
    prisoner_dob = serializers.DateField(required=False)
    prisoner_number = serializers.CharField(required=False)

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
            'reference_in_sender_field'
        )


class UpdateTransactionListSerializer(serializers.ListSerializer):

    @db_transaction.atomic
    def update(self, instance, validated_data):
        user = self.context['request'].user

        to_refund = [t['id'] for t in validated_data if t['refunded']]

        updated_transactions = []
        if to_refund:
            self.refund(user, to_refund)
            updated_transactions = Transaction.objects.filter(pk__in=to_refund)

        return updated_transactions

    def refund(self, user, to_refund):
        update_set = Credit.objects.filter(
            transaction__pk__in=to_refund,
            **Credit.STATUS_LOOKUP['refund_pending']).select_for_update()
        if len(update_set) != len(to_refund):
            raise Credit.DoesNotExist(
                list(set(to_refund) - {c.transaction.id for c in update_set})
            )

        updated_credits = list(update_set)
        update_set.update(resolution=CREDIT_RESOLUTION.REFUNDED)

        for credit in updated_credits:
            credit.resolution = CREDIT_RESOLUTION.REFUNDED
            credit_refunded.send(
                sender=Credit,
                credit=credit,
                by_user=user
            )

        return updated_credits


class UpdateRefundedTransactionSerializer(serializers.ModelSerializer):
    id = fields.IntegerField(required=True)
    refunded = fields.BooleanField(required=True)

    class Meta:
        model = Transaction
        list_serializer_class = UpdateTransactionListSerializer
        fields = (
            'id',
            'refunded'
        )


class TransactionSerializer(serializers.ModelSerializer):
    prison = PrisonSerializer(required=False)
    credited = fields.BooleanField()
    refunded = fields.BooleanField()

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
            'ref_code'
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
            'ref_code'
        )
