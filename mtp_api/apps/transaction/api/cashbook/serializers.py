from rest_framework import serializers

from transaction.models import Transaction


class CashbookCreditedOnlyTransactionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=True)
    credited = serializers.BooleanField(required=True)

    class Meta:
        model = Transaction
        fields = (
            'id',
            'credited',
        )


class CashbookTransactionSerializer(serializers.ModelSerializer):
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
