from rest_framework import serializers

from prison.models import Prison
from security.models import (
    SenderProfile, BankTransferSenderDetails, DebitCardSenderDetails,
    PrisonerProfile, RecipientProfile, BankTransferRecipientDetails,
    SavedSearch, SearchFilter,
)


class BankTransferSenderDetailsSerializer(serializers.ModelSerializer):
    sender_sort_code = serializers.CharField(
        source='sender_bank_account.sort_code'
    )
    sender_account_number = serializers.CharField(
        source='sender_bank_account.account_number'
    )
    sender_roll_number = serializers.CharField(
        source='sender_bank_account.roll_number'
    )

    class Meta:
        model = BankTransferSenderDetails
        fields = (
            'sender_name',
            'sender_sort_code',
            'sender_account_number',
            'sender_roll_number',
        )


class DebitCardSenderDetailsSerializer(serializers.ModelSerializer):
    cardholder_names = serializers.SerializerMethodField()
    sender_emails = serializers.SerializerMethodField()

    class Meta:
        model = DebitCardSenderDetails
        fields = (
            'card_number_last_digits',
            'card_expiry_date',
            'cardholder_names',
            'sender_emails',
            'postcode',
        )

    def get_cardholder_names(self, obj):
        return list(obj.cardholder_names.values_list('name', flat=True))

    def get_sender_emails(self, obj):
        return list(obj.sender_emails.values_list('email', flat=True))


class PrisonSerializer(serializers.ModelSerializer):
    """
    Serializer for nested prison fields.
    """

    class Meta:
        model = Prison
        fields = (
            'nomis_id',
            'name',
        )


class SenderProfileSerializer(serializers.ModelSerializer):
    prisons = PrisonSerializer(many=True)

    bank_transfer_details = BankTransferSenderDetailsSerializer(many=True)
    debit_card_details = DebitCardSenderDetailsSerializer(many=True)

    # return None where this is a nested serializer
    prisoner_count = serializers.IntegerField(required=False)
    prison_count = serializers.IntegerField(required=False)
    monitoring = serializers.BooleanField(required=False)

    class Meta:
        model = SenderProfile
        fields = (
            'id',
            'credit_count',
            'credit_total',
            'prisons',
            'prisoner_count',
            'prison_count',
            'bank_transfer_details',
            'debit_card_details',
            'created',
            'modified',
            'monitoring',
        )


class PrisonerProfileSerializer(serializers.ModelSerializer):
    prisons = PrisonSerializer(many=True)
    current_prison = PrisonSerializer()
    provided_names = serializers.SerializerMethodField()

    # return None where this is a nested serializer
    sender_count = serializers.IntegerField(required=False)
    recipient_count = serializers.IntegerField(required=False)
    monitoring = serializers.BooleanField(required=False)

    class Meta:
        model = PrisonerProfile
        fields = (
            'id',
            'credit_count',
            'credit_total',
            'disbursement_count',
            'disbursement_total',
            'sender_count',
            'recipient_count',
            'prisoner_name',
            'prisoner_number',
            'prisoner_dob',
            'created',
            'modified',
            'prisons',
            'current_prison',
            'provided_names',
            'monitoring',
        )

    def get_provided_names(self, obj):
        return list(obj.provided_names.values_list('name', flat=True))


class BankTransferRecipientDetailsSerializer(serializers.ModelSerializer):
    recipient_sort_code = serializers.CharField(
        source='recipient_bank_account.sort_code'
    )
    recipient_account_number = serializers.CharField(
        source='recipient_bank_account.account_number'
    )
    recipient_roll_number = serializers.CharField(
        source='recipient_bank_account.roll_number'
    )

    class Meta:
        model = BankTransferRecipientDetails
        fields = (
            'recipient_sort_code',
            'recipient_account_number',
            'recipient_roll_number',
        )


class RecipientProfileSerializer(serializers.ModelSerializer):
    bank_transfer_details = BankTransferRecipientDetailsSerializer(many=True)

    # return None where this is a nested serializer
    prisoner_count = serializers.IntegerField(required=False)
    prison_count = serializers.IntegerField(required=False)
    monitoring = serializers.BooleanField(required=False)

    class Meta:
        model = RecipientProfile
        fields = (
            'id',
            'disbursement_count',
            'disbursement_total',
            'prisoner_count',
            'prison_count',
            'bank_transfer_details',
            'created',
            'modified',
            'monitoring',
        )


class SearchFilterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchFilter
        fields = ('field', 'value',)


class SavedSearchSerializer(serializers.ModelSerializer):
    filters = SearchFilterSerializer(many=True)
    last_result_count = serializers.IntegerField(required=False)
    site_url = serializers.CharField(required=False)

    class Meta:
        model = SavedSearch
        read_only_fields = ('id',)
        fields = (
            'id',
            'description',
            'endpoint',
            'last_result_count',
            'site_url',
            'filters',
        )

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        filters = validated_data.pop('filters', [])
        saved_search = super().create(validated_data)
        for searchfilter in filters:
            SearchFilter.objects.create(saved_search=saved_search, **searchfilter)
        return saved_search

    def update(self, instance, validated_data):
        filters = validated_data.pop('filters', [])
        instance.filters.all().delete()
        for searchfilter in filters:
            SearchFilter.objects.create(saved_search=instance, **searchfilter)
        return super().update(instance, validated_data)
