from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from extended_choices import Choices
from model_utils.models import TimeStampedModel

from prison.models import Prison, PrisonerLocation
from .constants import LOG_ACTIONS
from .managers import LogManager
from .signals import (
    credit_created, credit_locked, credit_unlocked, credit_credited,
    credit_refunded, credit_reconciled
)

CREDIT_RESOLUTION = Choices(
    ('PENDING', 'pending', 'Pending'),
    ('CREDITED', 'credited', 'Credited'),
    ('REFUNDED', 'refunded', 'Refunded')
)


class Credit(TimeStampedModel):
    amount = models.PositiveIntegerField()
    prisoner_number = models.CharField(blank=True, null=True, max_length=250)
    prisoner_dob = models.DateField(blank=True, null=True)
    received_at = models.DateTimeField(auto_now=False, null=True)

    prisoner_name = models.CharField(blank=True, null=True, max_length=250)
    prison = models.ForeignKey(Prison, blank=True, null=True, on_delete=models.SET_NULL)

    resolution = models.CharField(max_length=50, choices=CREDIT_RESOLUTION, default=CREDIT_RESOLUTION.PENDING)
    reconciled = models.BooleanField(default=False)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        permissions = (
            ('view_credit', 'Can view credit'),
            ('lock_credit', 'Can lock credit'),
            ('unlock_credit', 'Can unlock credit'),
            ('patch_credited_credit', 'Can patch credited credit'),
        )
        index_together = (
            ('prisoner_number', 'prisoner_dob'),
        )


class Log(TimeStampedModel):
    credit = models.ForeignKey(Credit, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='credit_log'
    )
    action = models.CharField(max_length=50, choices=LOG_ACTIONS)

    objects = LogManager()

    def __str__(self):
        return 'Credit {id} {action} by {user}'.format(
            id=self.credit.pk,
            user='<None>' if not self.user else self.user.username,
            action=self.action
        )


@receiver(post_save, sender=Credit, dispatch_uid='update_prison_for_credit')
def update_prison_for_credit(sender, instance, created, *args, **kwargs):
    if (created and
            instance.reconciled is False and
            instance.resolution is CREDIT_RESOLUTION.PENDING and
            instance.owner is None):
        try:
            location = PrisonerLocation.objects.get(
                prisoner_number=instance.prisoner_number,
                prisoner_dob=instance.prisoner_dob
            )
            instance.prisoner_name = location.prisoner_name
            instance.prison = location.prison
            instance.save()
        except PrisonerLocation.DoesNotExist:
            pass


@receiver(credit_created)
def credit_created_receiver(sender, credit, by_user, **kwargs):
    Log.objects.credit_created(credit, by_user)


@receiver(credit_locked)
def credit_locked_receiver(sender, credit, by_user, **kwargs):
    Log.objects.credit_locked(credit, by_user)


@receiver(credit_unlocked)
def credit_unlocked_receiver(sender, credit, by_user, **kwargs):
    Log.objects.credit_unlocked(credit, by_user)


@receiver(credit_credited)
def credit_credited_receiver(sender, credit, by_user, credited=True, **kwargs):
    Log.objects.credit_credited(credit, by_user, credited=credited)


@receiver(credit_refunded)
def credit_refunded_receiver(sender, credit, by_user, **kwargs):
    Log.objects.credit_refunded(credit, by_user)


@receiver(credit_reconciled)
def credit_reconciled_receiver(sender, credit, by_user, **kwargs):
    Log.objects.credit_reconciled(credit, by_user)
