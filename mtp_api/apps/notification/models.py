from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from credit.models import Credit
from disbursement.models import Disbursement
from notification.constants import EMAIL_FREQUENCY
from security.models import (
    SenderProfile, RecipientProfile, PrisonerProfile,
)


def validate_rule_code(value):
    from notification.rules import RULES

    if value not in RULES:
        raise ValidationError(_('"%s" is not a recognised rule') % value)


class Event(models.Model):
    """
    Represents a single notification and has one-to-one relations to:
    - a single credit or disbursement
    - a prisoner, sender or recipient profile if relevant to this notification
      (currently this only happens when a user monitors those profiles)

    NB: multiple events can be created for the same credit or disbursement,
    e.g. a user monitoring both a sender and prisoner will get 2 notifications
    for a single credit from the former to the latter
    """
    rule = models.CharField(max_length=8, validators=[validate_rule_code])
    description = models.CharField(max_length=500, blank=True)
    triggered_at = models.DateTimeField(null=True, blank=True)
    # if `user` is None, the event is visible to all users (who subscribe to the rule)
    # if `user` is not None, the event is visible only to that user
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        indexes = [
            models.Index(fields=['-triggered_at', 'id']),
            models.Index(fields=['rule']),
        ]


class CreditEvent(models.Model):
    """
    Links a notification to a credit
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='credit_event'
    )
    credit = models.ForeignKey(Credit, on_delete=models.CASCADE)


class DisbursementEvent(models.Model):
    """
    Links a notification to a disbursement
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='disbursement_event'
    )
    disbursement = models.ForeignKey(Disbursement, on_delete=models.CASCADE)


class SenderProfileEvent(models.Model):
    """
    Links a notification to a sender profile
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='sender_profile_event'
    )
    sender_profile = models.ForeignKey(SenderProfile, on_delete=models.CASCADE)


class RecipientProfileEvent(models.Model):
    """
    Links a notification to a recipient profile
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='recipient_profile_event'
    )
    recipient_profile = models.ForeignKey(RecipientProfile, on_delete=models.CASCADE)


class PrisonerProfileEvent(models.Model):
    """
    Links a notification to a prisoner profile
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='prisoner_profile_event'
    )
    prisoner_profile = models.ForeignKey(PrisonerProfile, on_delete=models.CASCADE)


class EmailNotificationPreferences(models.Model):
    """
    Indicates that a user wishes to receive notifications by email
    NB: only DAILY is currently supported in noms-ops and email-sending management command
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    frequency = models.CharField(max_length=50, choices=EMAIL_FREQUENCY)
    last_sent_at = models.DateField(blank=True, null=True)
