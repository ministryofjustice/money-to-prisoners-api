from rest_framework import serializers

from credit.serializers import SecurityCreditSerializer
from disbursement.serializers import DisbursementSerializer
from notification.models import Event
from security.serializers import (
    PrisonerProfileSerializer, SenderProfileSerializer,
    RecipientProfileSerializer
)


class EventSerializer(serializers.ModelSerializer):
    credit = SecurityCreditSerializer(source='credit_event.credit')
    disbursement = DisbursementSerializer(source='disbursement_event.disbursement')
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
            'credit',
            'disbursement',
            'sender_profile',
            'recipient_profile',
            'prisoner_profile',
            'triggered_at',
            'rule',
            'description',
        )
