from django.db.transaction import atomic
from rest_framework import serializers

from .models import Payment
from .constants import PAYMENT_STATUS
from .exceptions import InvalidStateForUpdateException


class PaymentSerializer(serializers.ModelSerializer):

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
        fields = '__all__'
