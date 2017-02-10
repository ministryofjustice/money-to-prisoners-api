from rest_framework import serializers

from prison.models import Prison
from .models import (
    SenderProfile, BankTransferSenderDetails, DebitCardSenderDetails,
    PrisonerProfile
)


class BankTransferSenderDetailsSerializer(serializers.ModelSerializer):

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
        )

    def get_cardholder_names(self, obj):
        return list(obj.cardholder_names.values_list('name', flat=True))

    def get_sender_emails(self, obj):
        return list(obj.sender_emails.values_list('email', flat=True))


class SenderProfileSerializer(serializers.ModelSerializer):
    bank_transfer_details = BankTransferSenderDetailsSerializer(many=True)
    debit_card_details = DebitCardSenderDetailsSerializer(many=True)
    prisoner_count = serializers.IntegerField()
    prison_count = serializers.SerializerMethodField()

    class Meta:
        model = SenderProfile
        fields = (
            'id',
            'credit_count',
            'credit_total',
            'prisoner_count',
            'prison_count',
            'bank_transfer_details',
            'debit_card_details',
            'created',
            'modified',
        )

    def get_prison_count(self, obj):
        return sum(prisoner_profile.prisons.all().count() for prisoner_profile in obj.prisoners.all())


class PrisonSerializer(serializers.ModelSerializer):

    class Meta:
        model = Prison
        fields = (
            'nomis_id',
            'name'
        )


class PrisonerProfileSerializer(serializers.ModelSerializer):
    sender_count = serializers.IntegerField()
    prisons = PrisonSerializer(many=True)
    current_prison = PrisonSerializer()

    class Meta:
        model = PrisonerProfile
        fields = (
            'id',
            'credit_count',
            'credit_total',
            'sender_count',
            'prisoner_name',
            'prisoner_number',
            'prisoner_dob',
            'created',
            'modified',
            'prisons',
            'current_prison'
        )
