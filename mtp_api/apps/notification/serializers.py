from rest_framework import serializers

from credit.serializers import SecurityCreditSerializer
from disbursement.serializers import DisbursementSerializer
from security.serializers import (
    PrisonerProfileSerializer, SenderProfileSerializer,
    RecipientProfileSerializer
)
from .models import Event


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
    seen = serializers.SerializerMethodField()

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
            'seen',
        )

    def get_seen(self, obj):
        # returns True where this is a nested serializer, because it's probably
        # not worth the extra queries (unless it turns out it is)
        return getattr(obj, 'seen', True)
