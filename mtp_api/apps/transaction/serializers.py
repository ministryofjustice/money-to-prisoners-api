from rest_framework import serializers

from .models import Transaction


class TransactionSerializer(serializers.HyperlinkedModelSerializer):
    sender = serializers.SerializerMethodField()

    def get_sender(self, obj):
        return ''.join([
            obj.sender_bank_reference,
            obj.sender_customer_reference
        ])

    class Meta:
        model = Transaction
        fields = (
            'id', 'prisoner_number', 'prisoner_name', 'prisoner_dob',
            'amount', 'sender', 'received_at'
        )
