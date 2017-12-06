from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from mtp_auth.models import PrisonUserMapping
from prison.models import PrisonerLocation, Prison
from .models import Disbursement
from .signals import disbursement_created


class PrisonerInPrisonValidator():
    def __call__(self, data):
        prisoner_number = data['prisoner_number']
        prison = data['prison']

        try:
            PrisonerLocation.objects.get(
                prisoner_number=prisoner_number,
                prison=prison
            )
        except PrisonerLocation.DoesNotExist:
            raise serializers.ValidationError(
                _('Prisoner %(prisoner_number)s is not in %(prison)s') %
                {'prisoner_number': prisoner_number, 'prison': prison}
            )


class PrisonPermittedValidator():
    def set_context(self, serializer):
        self.user = serializer.context['request'].user

    def __call__(self, value):
        if (
            value not in
            PrisonUserMapping.objects.get_prison_set_for_user(self.user)
        ):
            raise serializers.ValidationError(
                _('Cannot create a disbursement for this prison')
            )


class DisbursementSerializer(serializers.ModelSerializer):
    prison = serializers.PrimaryKeyRelatedField(
        queryset=Prison.objects.all(),
        validators=[PrisonPermittedValidator()]
    )

    @atomic
    def create(self, *args, **kwargs):
        new_disbursement = super().create(*args, **kwargs)
        disbursement_created.send(
            sender=Disbursement,
            disbursement=new_disbursement,
            by_user=self.context['request'].user
        )
        return new_disbursement

    class Meta:
        model = Disbursement
        fields = '__all__'
        validators = [PrisonerInPrisonValidator()]


class DisbursementIdsSerializer(serializers.Serializer):
    disbursement_ids = serializers.ListField(child=serializers.IntegerField())
