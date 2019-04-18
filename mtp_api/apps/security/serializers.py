from rest_framework import serializers

from prison.models import Prison
from .models import (
    SenderProfile, BankTransferSenderDetails, DebitCardSenderDetails,
    PrisonerProfile, SavedSearch, SearchFilter, SenderTotals, PrisonerTotals,
    RecipientProfile, RecipientTotals, BankTransferRecipientDetails
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


class SenderTotalsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SenderTotals
        fields = '__all__'


class SenderProfileSerializer(serializers.ModelSerializer):
    bank_transfer_details = BankTransferSenderDetailsSerializer(many=True)
    debit_card_details = DebitCardSenderDetailsSerializer(many=True)
    totals = SenderTotalsSerializer(many=True)
    monitoring = serializers.SerializerMethodField()

    class Meta:
        model = SenderProfile
        fields = (
            'id',
            'bank_transfer_details',
            'debit_card_details',
            'created',
            'modified',
            'totals',
            'monitoring',
        )

    def get_monitoring(self, obj):
        # returns None where this is a nested serializer, because it's probably
        # not worth the extra queries (unless it turns out it is)
        return getattr(obj, 'monitoring', None)


class PrisonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prison
        fields = (
            'nomis_id',
            'name'
        )


class PrisonerTotalsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrisonerTotals
        fields = '__all__'


class PrisonerProfileSerializer(serializers.ModelSerializer):
    prisons = PrisonSerializer(many=True)
    current_prison = PrisonSerializer()
    provided_names = serializers.SerializerMethodField()
    totals = PrisonerTotalsSerializer(many=True)
    monitoring = serializers.SerializerMethodField()

    class Meta:
        model = PrisonerProfile
        fields = (
            'id',
            'prisoner_name',
            'prisoner_number',
            'prisoner_dob',
            'created',
            'modified',
            'prisons',
            'current_prison',
            'provided_names',
            'totals',
            'monitoring',
        )

    def get_monitoring(self, obj):
        # returns None where this is a nested serializer, because it's probably
        # not worth the extra queries (unless it turns out it is)
        return getattr(obj, 'monitoring', None)

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


class RecipientTotalsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipientTotals
        fields = '__all__'


class RecipientProfileSerializer(serializers.ModelSerializer):
    bank_transfer_details = BankTransferRecipientDetailsSerializer(many=True)
    totals = RecipientTotalsSerializer(many=True)
    monitoring = serializers.SerializerMethodField()

    class Meta:
        model = RecipientProfile
        fields = (
            'id',
            'bank_transfer_details',
            'created',
            'modified',
            'totals',
            'monitoring',
        )

    def get_monitoring(self, obj):
        # returns None where this is a nested serializer, because it's probably
        # not worth the extra queries (unless it turns out it is)
        return getattr(obj, 'monitoring', None)


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
