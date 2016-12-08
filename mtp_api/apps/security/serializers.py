from rest_framework import serializers

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

    class Meta:
        model = DebitCardSenderDetails
        fields = (
            'card_number_last_digits',
            'card_expiry_date',
            'cardholder_names',
        )

    def get_cardholder_names(self, obj):
        return list(obj.cardholder_names.values_list('name', flat=True))


class SenderProfileSerializer(serializers.ModelSerializer):
    bank_transfer_details = BankTransferSenderDetailsSerializer(many=True)
    debit_card_details = DebitCardSenderDetailsSerializer(many=True)
    prisoner_count = serializers.IntegerField()

    class Meta:
        model = SenderProfile
        fields = (
            'id',
            'credit_count',
            'credit_total',
            'prisoner_count',
            'bank_transfer_details',
            'debit_card_details',
            'created',
            'modified',
        )


class PrisonerProfileSerializer(serializers.ModelSerializer):
    sender_count = serializers.IntegerField()

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
            'prisons',
            'created',
            'modified',
        )
