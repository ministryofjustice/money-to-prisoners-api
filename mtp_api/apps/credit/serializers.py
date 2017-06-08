from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from prison.models import Prison
from .models import Credit, Comment, ProcessingBatch

User = get_user_model()


class CreditedOnlyCreditSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=True)
    credited = serializers.BooleanField(required=True)
    nomis_transaction_id = serializers.CharField(required=False)

    class Meta:
        model = Credit
        fields = (
            'id',
            'credited',
            'nomis_transaction_id',
        )


class IdsCreditSerializer(serializers.Serializer):
    credit_ids = serializers.ListField(child=serializers.IntegerField())


class CommentSerializer(serializers.ModelSerializer):
    user_full_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Comment
        read_only = ('user',)
        fields = ('credit', 'user', 'user_full_name', 'comment',)

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        super().create(validated_data)

    def get_user_full_name(self, obj):
        return obj.user.get_full_name() if obj.user else None


class CreditSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(read_only=True)
    sender_email = serializers.CharField(read_only=True)
    owner_name = serializers.CharField(read_only=True)
    credited_at = serializers.DateTimeField(read_only=True)
    refunded_at = serializers.DateTimeField(read_only=True)
    source = serializers.CharField(read_only=True)
    intended_recipient = serializers.CharField(read_only=True)
    anonymous = serializers.SerializerMethodField()
    reconciliation_code = serializers.CharField(read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    short_payment_ref = serializers.SerializerMethodField()

    class Meta:
        model = Credit
        fields = (
            'id',
            'prisoner_name',
            'prisoner_number',
            'amount',
            'received_at',
            'sender_name',
            'sender_email',
            'prison',
            'owner',
            'owner_name',
            'resolution',
            'credited_at',
            'refunded_at',
            'source',
            'intended_recipient',
            'anonymous',
            'reconciliation_code',
            'comments',
            'reviewed',
            'short_payment_ref',
            'nomis_transaction_id',
        )

    def get_anonymous(self, obj):
        try:
            return obj.transaction.incomplete_sender_info and obj.blocked
        except AttributeError:
            return False

    def get_short_payment_ref(self, obj):
        try:
            return str(obj.payment.uuid)[:8].upper()
        except AttributeError:
            return None


class SecurityCreditSerializer(CreditSerializer):
    prison_name = serializers.SerializerMethodField()
    sender_sort_code = serializers.CharField(read_only=True)
    sender_account_number = serializers.CharField(read_only=True)
    sender_roll_number = serializers.CharField(read_only=True)
    card_number_last_digits = serializers.CharField(read_only=True)
    card_expiry_date = serializers.CharField(read_only=True)
    sender_profile = serializers.PrimaryKeyRelatedField(read_only=True)
    prisoner_profile = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Credit
        fields = CreditSerializer.Meta.fields + (
            'prison_name',
            'sender_sort_code',
            'sender_account_number',
            'sender_roll_number',
            'card_number_last_digits',
            'card_expiry_date',
            'sender_profile',
            'prisoner_profile',
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


class ProcessingBatchSerializer(serializers.ModelSerializer):
    expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProcessingBatch
        read_only_fields = ('id', 'user', 'expired', 'created',)
        fields = ('id', 'user', 'credits', 'created', 'expired',)

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)


class CreditsGroupedByCreditedSerializer(serializers.Serializer):
    logged_at = serializers.DateField()
    owner = serializers.IntegerField()
    owner_name = serializers.SerializerMethodField()
    count = serializers.IntegerField()
    total = serializers.IntegerField()
    comment_count = serializers.IntegerField()

    def get_owner_name(self, instance):
        try:
            return User.objects.get(pk=instance['owner']).get_full_name()
        except User.DoesNotExist:
            return _('Unknown')
