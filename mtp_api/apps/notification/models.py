from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from credit.models import Credit
from disbursement.models import Disbursement
from security.models import (
    SenderProfile, RecipientProfile, PrisonerProfile
)
from .constants import EMAIL_FREQUENCY


def validate_rule_code(value):
    from .rules import RULES
    if value not in RULES:
        raise ValidationError(_('"%s" is not a recognised rule') % value)


class Event(models.Model):
    rule = models.CharField(max_length=8, validators=[validate_rule_code])
    description = models.CharField(max_length=500, blank=True)
    triggered_at = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        permissions = (
            ('view_event', 'Can view event'),
        )
        indexes = [
            models.Index(fields=['-triggered_at', 'id']),
            models.Index(fields=['rule']),
        ]


class CreditEvent(models.Model):
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='credit_event'
    )
    credit = models.ForeignKey(Credit, on_delete=models.CASCADE)


class DisbursementEvent(models.Model):
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='disbursement_event'
    )
    disbursement = models.ForeignKey(Disbursement, on_delete=models.CASCADE)


class SenderProfileEvent(models.Model):
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='sender_profile_event'
    )
    sender_profile = models.ForeignKey(SenderProfile, on_delete=models.CASCADE)


class RecipientProfileEvent(models.Model):
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='recipient_profile_event'
    )
    recipient_profile = models.ForeignKey(RecipientProfile, on_delete=models.CASCADE)


class PrisonerProfileEvent(models.Model):
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='prisoner_profile_event'
    )
    prisoner_profile = models.ForeignKey(PrisonerProfile, on_delete=models.CASCADE)


class EmailNotificationPreferences(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    frequency = models.CharField(max_length=50, choices=EMAIL_FREQUENCY)
