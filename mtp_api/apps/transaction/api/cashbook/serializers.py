from rest_framework import serializers

from transaction.models import Transaction


class CreditedOnlyTransactionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=True)
    credited = serializers.BooleanField(required=True)

    class Meta:
        model = Transaction
        fields = (
            'id',
            'credited',
        )


class IdsTransactionSerializer(serializers.Serializer):
    transaction_ids = serializers.ListField(
       child=serializers.IntegerField()
    )


class TransactionSerializer(serializers.ModelSerializer):
    sender = serializers.CharField(source='sender_name')
    owner_name = serializers.CharField(read_only=True)
    credited_at = serializers.DateTimeField(read_only=True)
    refunded_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Transaction
        fields = (
            'id',
            'prisoner_name',
            'prisoner_number',
            'amount',
            'sender',
            'received_at',
            'prison',
            'owner',
            'owner_name',
            'credited',
            'credited_at',
            'refunded',
            'refunded_at',
        )


class LockedTransactionSerializer(TransactionSerializer):
    locked = serializers.BooleanField(read_only=True)
    locked_at = serializers.DateTimeField(read_only=True)

    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + (
            'locked',
            'locked_at',
        )
