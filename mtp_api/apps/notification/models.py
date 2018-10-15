from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from credit.models import Credit
from disbursement.models import Disbursement


def validate_rule_code(value):
    from .rules import RULES
    if value not in RULES:
        raise ValidationError(_('"%s" is not a recognised rule') % value)


class Subscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )
    rule = models.CharField(max_length=8, validators=[validate_rule_code])
    start = models.DateTimeField(default=timezone.now)

    class Meta:
        permissions = (
            ('view_subscription', 'Can view subscription'),
        )

    def create_events(self):
        from .rules import RULES
        RULES[self.rule].create_events(self)


class Parameter(models.Model):
    field = models.CharField(max_length=250)
    value = models.CharField(max_length=250)
    exclude = models.BooleanField(default=False)
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name='parameters',
    )


class Event(TimeStampedModel):
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name='events',
    )
    ref_number = models.IntegerField()
    email_sent = models.BooleanField(default=False)
    credits = models.ManyToManyField(
        Credit, through='EventCredit', related_name='events'
    )
    disbursements = models.ManyToManyField(
        Disbursement, through='EventDisbursement', related_name='events'
    )

    class Meta:
        permissions = (
            ('view_event', 'Can view event'),
        )


class EventCredit(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    credit = models.ForeignKey(Credit, on_delete=models.CASCADE)
    triggering = models.BooleanField(default=False)


class EventDisbursement(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    disbursement = models.ForeignKey(Disbursement, on_delete=models.CASCADE)
    triggering = models.BooleanField(default=False)
