from rest_framework import serializers

from .models import Credit


class CreditedOnlyCreditSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=True)
    credited = serializers.BooleanField(required=True)

    class Meta:
        model = Credit
        fields = (
            'id',
            'credited',
        )


class IdsCreditSerializer(serializers.Serializer):
    credit_ids = serializers.ListField(
       child=serializers.IntegerField()
    )


class CreditSerializer(serializers.ModelSerializer):
    sender = serializers.CharField(read_only=True)
    owner_name = serializers.CharField(read_only=True)
    credited_at = serializers.DateTimeField(read_only=True)
    refunded_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Credit
        fields = (
            'id',
            'prisoner_name',
            'prisoner_number',
            'amount',
            'received_at',
            'sender',
            'prison',
            'owner',
            'owner_name',
            'resolution',
            'credited_at',
            'refunded_at',
        )


class SecurityCreditSerializer(serializers.ModelSerializer):
    sender = serializers.CharField(read_only=True)
    sender_sort_code = serializers.CharField(read_only=True)
    sender_account_number = serializers.CharField(read_only=True)
    sender_roll_number = serializers.CharField(read_only=True)
    owner_name = serializers.CharField(read_only=True)
    credited_at = serializers.DateTimeField(read_only=True)
    refunded_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Credit
        fields = (
            'id',
            'prisoner_name',
            'prisoner_number',
            'amount',
            'received_at',
            'sender',
            'sender_sort_code',
            'sender_account_number',
            'sender_roll_number',
            'prison',
            'owner',
            'owner_name',
            'resolution',
            'credited_at',
            'refunded_at',
        )


class LockedCreditSerializer(CreditSerializer):
    locked = serializers.BooleanField(read_only=True)
    locked_at = serializers.DateTimeField(read_only=True)

    class Meta(CreditSerializer.Meta):
        fields = CreditSerializer.Meta.fields + (
            'locked',
            'locked_at',
        )


class RecipientSerializer(serializers.Serializer):
    prisoner_number = serializers.CharField()
    prisoner_name = serializers.CharField()
    credit_total = serializers.IntegerField()
    credit_count = serializers.IntegerField()

    class Meta:
        fields = (
            'prisoner_number',
            'prisoner_name',
            'credit_total',
            'credit_count',
        )


class SenderSerializer(serializers.Serializer):
    sender = serializers.CharField(required=False)
    sender_sort_code = serializers.CharField(required=False)
    sender_account_number = serializers.CharField(required=False)
    sender_roll_number = serializers.CharField(required=False)
    recipient_count = serializers.IntegerField()
    recipients = RecipientSerializer(many=True)

    class Meta:
        fields = (
            'sender',
            'sender_sort_code',
            'sender_account_number',
            'sender_roll_number',
            'recipient_count',
            'recipients',
        )
