from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from credit.models import Credit
from disbursement.models import Disbursement
from notification.constants import EmailFrequency
from security.models import SenderProfile, RecipientProfile, PrisonerProfile


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
    rule = models.CharField(
        max_length=8, validators=[validate_rule_code],
        db_comment='Code of the rule that created the notification.',
    )
    description = models.CharField(max_length=500, blank=True, db_comment='Text of the notification.')
    triggered_at = models.DateTimeField(
        null=True, blank=True,
        db_comment='When the credit was received or the disbursement was created.',
    )
    # if `user` is None, the event is visible to all users (who subscribe to the rule)
    # if `user` is not None, the event is visible only to that user
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE,
        db_comment='The user the notification is for; empty if it is for everyone who follows the rule.',
    )

    class Meta:
        db_table_comment = (
            'Notifications: notifications shown to security staff in NOMS Ops about a credit or disbursement. '
            'There can be more than one for the same credit or disbursement.'
        )
        indexes = [
            models.Index(fields=['-triggered_at', 'id']),
            models.Index(fields=['rule']),
        ]


class CreditEvent(models.Model):
    """
    Links a notification to a credit
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='credit_event',
        db_comment='The notification.',
    )
    credit = models.ForeignKey(Credit, on_delete=models.CASCADE, db_comment='The credit it is about.')

    class Meta:
        db_table_comment = 'Notifications: links a notification to the credit it is about.'


class DisbursementEvent(models.Model):
    """
    Links a notification to a disbursement
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='disbursement_event',
        db_comment='The notification.',
    )
    disbursement = models.ForeignKey(Disbursement, on_delete=models.CASCADE, db_comment='The disbursement it is about.')

    class Meta:
        db_table_comment = 'Notifications: links a notification to the disbursement it is about.'


class SenderProfileEvent(models.Model):
    """
    Links a notification to a sender profile
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='sender_profile_event',
        db_comment='The notification.',
    )
    sender_profile = models.ForeignKey(
        SenderProfile, on_delete=models.CASCADE,
        db_comment='The sender profile it is about.',
    )

    class Meta:
        db_table_comment = 'Notifications: links a notification to the sender profile it is about.'


class RecipientProfileEvent(models.Model):
    """
    Links a notification to a recipient profile
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='recipient_profile_event',
        db_comment='The notification.',
    )
    recipient_profile = models.ForeignKey(
        RecipientProfile, on_delete=models.CASCADE,
        db_comment='The recipient profile it is about.',
    )

    class Meta:
        db_table_comment = 'Notifications: links a notification to the recipient profile it is about.'


class PrisonerProfileEvent(models.Model):
    """
    Links a notification to a prisoner profile
    """
    event = models.OneToOneField(
        Event, on_delete=models.CASCADE, related_name='prisoner_profile_event',
        db_comment='The notification.',
    )
    prisoner_profile = models.ForeignKey(
        PrisonerProfile, on_delete=models.CASCADE,
        db_comment='The prisoner profile it is about.',
    )

    class Meta:
        db_table_comment = 'Notifications: links a notification to the prisoner profile it is about.'


class EmailNotificationPreferences(models.Model):
    """
    Indicates that a user wishes to receive notifications by email
    NB: only DAILY is currently supported in noms-ops and email-sending management command
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_comment='The user.')
    frequency = models.CharField(
        max_length=50, choices=EmailFrequency.choices,
        db_comment='How often to send the email. Only daily is currently used.',
    )
    last_sent_at = models.DateField(blank=True, null=True, db_comment='Day the last email was sent.')

    class Meta:
        db_table_comment = 'Notifications: users of NOMS Ops who have asked to be sent their notifications by email.'
