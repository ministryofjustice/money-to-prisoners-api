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
    anonymous = serializers.SerializerMethodField()

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
            'anonymous',
        )

    def get_anonymous(self, obj):
        try:
            return obj.transaction.incomplete_sender_info
        except AttributeError:
            return False


class SecurityCreditSerializer(CreditSerializer):
    prison_name = serializers.SerializerMethodField()
    sender_sort_code = serializers.CharField(read_only=True)
    sender_account_number = serializers.CharField(read_only=True)
    sender_roll_number = serializers.CharField(read_only=True)

    class Meta:
        model = Credit
        fields = CreditSerializer.Meta.fields + (
            'prison_name',
            'sender_sort_code',
            'sender_account_number',
            'sender_roll_number',
        )

    @classmethod
    def get_prison_name(cls, obj):
        try:
            return Prison.objects.get(pk=obj.prison_id).name
        except Prison.DoesNotExist:
            return None


class LockedCreditSerializer(CreditSerializer):
    locked = serializers.BooleanField(read_only=True)
    locked_at = serializers.DateTimeField(read_only=True)

    class Meta(CreditSerializer.Meta):
        fields = CreditSerializer.Meta.fields + (
            'locked',
            'locked_at',
        )


class BaseSenderSerializer(serializers.Serializer):
    sender_name = serializers.CharField(required=False)
    sender_sort_code = serializers.CharField(required=False)
    sender_account_number = serializers.CharField(required=False)
    sender_roll_number = serializers.CharField(required=False)


class BasePrisonerSerializer(serializers.Serializer):
    prisoner_number = serializers.CharField()
    prisoner_name = serializers.CharField()
    prison_id = serializers.CharField()
    prison_name = serializers.CharField()
    current_prison_name = serializers.CharField()


class DetailSenderSerializer(BaseSenderSerializer):
    credit_count = serializers.IntegerField()
    credit_total = serializers.IntegerField()


class DetailPrisonerSerializer(BasePrisonerSerializer):
    credit_count = serializers.IntegerField()
    credit_total = serializers.IntegerField()


class SenderSerializer(DetailSenderSerializer):
    prisoners = DetailPrisonerSerializer(many=True)
    prisoner_count = serializers.IntegerField()


class PrisonerSerializer(DetailPrisonerSerializer):
    senders = DetailSenderSerializer(many=True)
    sender_count = serializers.IntegerField()
