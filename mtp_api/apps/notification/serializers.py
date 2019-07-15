from rest_framework import serializers

from notification.models import Event
from security.serializers import (
    PrisonerProfileSerializer, SenderProfileSerializer, RecipientProfileSerializer,
)


class EventSerializer(serializers.ModelSerializer):
    credit_id = serializers.IntegerField(source='credit_event.credit.id')
    disbursement_id = serializers.IntegerField(source='disbursement_event.disbursement.id')
    sender_profile = SenderProfileSerializer(
        source='sender_profile_event.sender_profile'
    )
    recipient_profile = RecipientProfileSerializer(
        source='recipient_profile_event.recipient_profile'
    )
    prisoner_profile = PrisonerProfileSerializer(
        source='prisoner_profile_event.prisoner_profile'
    )

    class Meta:
        model = Event
        fields = (
            'id',
            'credit_id',
            'disbursement_id',
            'sender_profile',
            'recipient_profile',
            'prisoner_profile',
            'triggered_at',
            'rule',
            'description',
        )
