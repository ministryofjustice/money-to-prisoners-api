from django.conf import settings
from django.db import models
from django.dispatch import receiver
from model_utils.models import TimeStampedModel

from .constants import LOG_ACTIONS, DISBURSEMENT_RESOLUTION, DISBURSEMENT_METHOD
from .managers import DisbursementManager, DisbursementQuerySet, LogManager
from .signals import (
    disbursement_confirmed, disbursement_created, disbursement_rejected,
    disbursement_sent
)
from prison.models import Prison
from transaction.utils import format_amount


class Disbursement(TimeStampedModel):
    amount = models.PositiveIntegerField()
    prisoner_number = models.CharField(max_length=250)
    prison = models.ForeignKey(Prison, on_delete=models.PROTECT)
    resolution = models.CharField(
        max_length=50, choices=DISBURSEMENT_RESOLUTION,
        default=DISBURSEMENT_RESOLUTION.PENDING
    )
    method = models.CharField(max_length=50, choices=DISBURSEMENT_METHOD)

    # recipient details
    recipient_first_name = models.CharField(max_length=250)
    recipient_last_name = models.CharField(max_length=250)
    recipient_email = models.EmailField(null=True, blank=True)

    address_line1 = models.CharField(max_length=250, blank=True, null=True)
    address_line2 = models.CharField(max_length=250, blank=True, null=True)
    city = models.CharField(max_length=250, blank=True, null=True)
    postcode = models.CharField(max_length=250, blank=True, null=True)
    country = models.CharField(max_length=250, blank=True, null=True)

    sort_code = models.CharField(max_length=50, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    # used by building societies to identify the account nr
    roll_number = models.CharField(max_length=50, blank=True, null=True)

    objects = DisbursementManager.from_queryset(DisbursementQuerySet)()

    @property
    def recipient_name(self):
        return '%s %s' % (self.recipient_first_name, self.recipient_last_name)

    def reject(self, by_user):
        self.resolution = DISBURSEMENT_RESOLUTION.REJECTED
        self.save()
        disbursement_rejected.send(Disbursement, self, by_user)

    def confirm(self, by_user):
        self.resolution = DISBURSEMENT_RESOLUTION.CONFIRMED
        self.save()
        disbursement_confirmed.send(Disbursement, self, by_user)

    def send(self, by_user):
        self.resolution = DISBURSEMENT_RESOLUTION.SENT
        self.save()
        disbursement_sent.send(Disbursement, self, by_user)

    class Meta:
        permissions = (
            ('view_disbursement', 'Can view disbursements'),
        )

    def __str__(self):
        return 'Disbursement {id}, {amount} {prisoner} > {recipient}, {status}'.format(
            id=self.pk,
            amount=format_amount(self.amount, True),
            prisoner=self.prisoner_number,
            recipient=self.recipient_name,
            status=self.resolution
        )


class Log(TimeStampedModel):
    disbursement = models.ForeignKey(Disbursement, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='disbursement_log'
    )
    action = models.CharField(max_length=50, choices=LOG_ACTIONS)

    objects = LogManager()

    def __str__(self):
        return 'Disbursement {id} {action} by {user}'.format(
            id=self.disbursement.pk,
            user='<None>' if not self.user else self.user.username,
            action=self.action
        )


@receiver(disbursement_created)
def disbursement_created_receiver(sender, disbursement, by_user, **kwargs):
    Log.objects.disbursements_created([disbursement], by_user)


@receiver(disbursement_rejected)
def disbursement_rejected_receiver(sender, disbursement, by_user, **kwargs):
    Log.objects.disbursements_rejected([disbursement], by_user)


@receiver(disbursement_confirmed)
def disbursement_confirmed_receiver(sender, disbursement, by_user, **kwargs):
    Log.objects.disbursements_confirmed([disbursement], by_user)


@receiver(disbursement_sent)
def disbursement_sent_receiver(sender, disbursement, by_user, **kwargs):
    Log.objects.disbursements_sent([disbursement], by_user)