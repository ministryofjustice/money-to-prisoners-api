from rest_framework import serializers
from rest_framework.fields import UUIDField, CharField, IntegerField


class AccountingBatchSerializer(serializers.ModelSerializer):

    id = IntegerField(source='transaction.id')
    upload_counter = IntegerField(source='transaction.upload_counter')
    prison = CharField(
        source='transaction.prison.nomis_id', required=False, allow_null=True, allow_blank=True)
    prisoner_number = CharField(
        source='transaction.prisoner_number', required=False, allow_null=True, allow_blank=True)
    prisoner_dob = CharField(
        source='transaction.prisoner_dob', required=False, allow_null=True, allow_blank=True)
    amount = CharField(source='transaction.amount')
    sender_bank_reference = CharField(
        source='transaction.sender_bank_reference', required=False, allow_null=True, allow_blank=True)
    sender_customer_reference = CharField(
        source='transaction.sender_customer_reference', required=False, allow_null=True, allow_blank=True)
    reference = CharField(source='transaction.reference',
                          required=False, allow_null=True, allow_blank=True)
    received_at = CharField(source='transaction.received_at')

    class Meta:
        fields = (
            # fields from transaction
            'id',
            'upload_counter',
            'prison',
            'prisoner_number',
            'prisoner_dob',
            'amount',
            'sender_bank_reference',
            'sender_customer_reference',
            'reference',
            'received_at',

            # fields from model
            'credited',
            'discarded',
            'locked_by'
        )


class NewBatchSerializer(serializers.Serializer):
    batch_reference = UUIDField()
    locked_by = CharField()
    transactions = AccountingBatchSerializer(many=True)
