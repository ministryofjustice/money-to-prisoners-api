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


class BaseRecipientSerializer(serializers.Serializer):
    prisoner_number = serializers.CharField()
    prisoner_name = serializers.CharField()

    class Meta:
        fields = (
            'prisoner_number',
            'prisoner_name'
        )


class DetailRecipientSerializer(BaseRecipientSerializer):
    credit_total = serializers.IntegerField()
    credit_count = serializers.IntegerField()

    class Meta:
        fields = BaseRecipientSerializer.Meta.fields + (
            'credit_total',
            'credit_count',
        )


class BaseSenderSerializer(serializers.Serializer):
    sender = serializers.CharField(required=False)
    sender_sort_code = serializers.CharField(required=False)
    sender_account_number = serializers.CharField(required=False)
    sender_roll_number = serializers.CharField(required=False)

    class Meta:
        fields = (
            'sender',
            'sender_sort_code',
            'sender_account_number',
            'sender_roll_number',
        )


class DetailSenderSerializer(BaseSenderSerializer):
    credit_total = serializers.IntegerField()
    credit_count = serializers.IntegerField()

    class Meta:
        fields = BaseSenderSerializer.Meta.fields + (
            'credit_total',
            'credit_count',
        )


class RecipientSerializer(BaseRecipientSerializer):
    sender_count = serializers.IntegerField()
    senders = DetailSenderSerializer(many=True)

    class Meta:
        fields = BaseRecipientSerializer.Meta.fields + (
            'sender_count',
            'senders',
        )


class SenderSerializer(BaseSenderSerializer):
    recipient_count = serializers.IntegerField()
    recipients = DetailRecipientSerializer(many=True)

    class Meta:
        fields = BaseSenderSerializer.Meta.fields + (
            'recipient_count',
            'recipients',
        )
