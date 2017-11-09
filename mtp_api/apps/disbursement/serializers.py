from django.db.transaction import atomic
from rest_framework import serializers

from .models import Disbursement, Recipient
from .signals import disbursement_created


class DisbursementSerializer(serializers.ModelSerializer):

    @atomic
    def create(self, *args, **kwargs):
        new_disbursement = super().create(*args, **kwargs)
        user = self.context['request'].user
        disbursement_created.send(
            sender=Disbursement,
            disbursement=new_disbursement,
            by_user=user
        )
        return new_disbursement

    class Meta:
        model = Disbursement
        fields = '__all__'


class DisbursementIdsSerializer(serializers.Serializer):
    disbursement_ids = serializers.ListField(child=serializers.IntegerField())


class RecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipient
        fields = '__all__'
