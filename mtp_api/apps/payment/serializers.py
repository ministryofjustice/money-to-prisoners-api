from django.db.transaction import atomic
from rest_framework import serializers

from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from .models import Payment
from .constants import PAYMENT_STATUS
from .exceptions import InvalidStateForUpdateException


class PaymentSerializer(serializers.ModelSerializer):
    prisoner_dob = serializers.DateField()
    prisoner_number = serializers.CharField()

    @atomic
    def create(self, validated_data):
        new_credit = Credit(
            amount=validated_data['amount'],
            prisoner_number=validated_data.pop('prisoner_number'),
            prisoner_dob=validated_data.pop('prisoner_dob'),
            resolution=CREDIT_RESOLUTION.INITIAL
        )
        new_credit.save()
        validated_data['credit'] = new_credit
        return super().create(validated_data)

    @atomic
    def update(self, instance, validated_data):
        if instance.status != PAYMENT_STATUS.PENDING:
            raise InvalidStateForUpdateException(
                'Payment cannot be updated in status "%s"'
                % instance.status
            )
        return super().update(instance, validated_data)

    class Meta:
        model = Payment
        read_only = ('uuid', 'prisoner_dob', 'prisoner_number')
        fields = (
            'uuid',
            'status',
            'processor_id',
            'amount',
            'service_charge',
            'recipient_name',
            'email',
            'prisoner_dob',
            'prisoner_number'
        )
