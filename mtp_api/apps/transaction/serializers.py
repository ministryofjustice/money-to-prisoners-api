from django.db import transaction
from django.db.models import Max

from rest_framework import serializers

from .signals import transaction_created
from .models import Transaction


class CreditedOnlyTransactionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=True)
    credited = serializers.BooleanField(required=True)

    class Meta:
        model = Transaction
        fields = (
            'id',
            'credited',
        )


class DefaultTransactionSerializer(serializers.ModelSerializer):
    sender = serializers.CharField(source='sender_name')

    class Meta:
        model = Transaction
        fields = (
            'id',
            'prisoner_number',
            'amount',
            'sender',
            'received_at',
            'prison',

            'owner',
            'credited',
        )


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
