from rest_framework import serializers

from prison.models import Prison
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
    sender_name = serializers.CharField(read_only=True)
    owner_name = serializers.CharField(read_only=True)
    credited_at = serializers.DateTimeField(read_only=True)
    refunded_at = serializers.DateTimeField(read_only=True)
    source = serializers.CharField(read_only=True)
    intended_recipient = serializers.CharField(read_only=True)

    class Meta:
        model = Credit
        fields = (
            'id',
            'prisoner_name',
            'prisoner_number',
            'amount',
            'received_at',
            'sender_name',
            'prison',
            'owner',
            'owner_name',
            'resolution',
            'credited_at',
            'refunded_at',
            'source',
            'intended_recipient',
        )


class SecurityCreditSerializer(CreditSerializer):
    sender_sort_code = serializers.CharField(read_only=True)
    sender_account_number = serializers.CharField(read_only=True)
    sender_roll_number = serializers.CharField(read_only=True)

    class Meta:
        model = Credit
        fields = CreditSerializer.Meta.fields + (
            'sender_sort_code',
            'sender_account_number',
            'sender_roll_number',
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
    prison_name = serializers.SerializerMethodField()

    @classmethod
    def get_prison_name(cls, obj):
        try:
            return Prison.objects.get(pk=obj['prison_id']).name
        except Prison.DoesNotExist:
            return None


class DetailRecipientSerializer(BaseRecipientSerializer):
    credit_total = serializers.IntegerField()
    credit_count = serializers.IntegerField()


class BaseSenderSerializer(serializers.Serializer):
    sender_name = serializers.CharField(required=False)
    sender_sort_code = serializers.CharField(required=False)
    sender_account_number = serializers.CharField(required=False)
    sender_roll_number = serializers.CharField(required=False)


class DetailSenderSerializer(BaseSenderSerializer):
    credit_total = serializers.IntegerField()
    credit_count = serializers.IntegerField()


class RecipientSerializer(BaseRecipientSerializer):
    sender_count = serializers.IntegerField()
    senders = DetailSenderSerializer(many=True)


class SenderSerializer(BaseSenderSerializer):
    recipient_count = serializers.IntegerField()
    recipients = DetailRecipientSerializer(many=True)
