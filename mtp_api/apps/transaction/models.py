from django.db import models
from django.db.models.signals import post_save
from django.conf import settings
from django.dispatch import receiver

from model_utils.models import TimeStampedModel

from prison.models import Prison

from .constants import TRANSACTION_STATUS, LOG_ACTIONS
from .managers import TransactionQuerySet, LogManager
from .signals import transaction_taken, transaction_released, \
    transaction_credited


class Transaction(TimeStampedModel):
    upload_counter = models.PositiveIntegerField()

    prison = models.ForeignKey(Prison, blank=True, null=True)

    prisoner_number = models.CharField(blank=True, max_length=250)
    prisoner_dob = models.DateField(blank=True, null=True)

    amount = models.PositiveIntegerField()
    sender_bank_reference = models.CharField(
        blank=True, max_length=250
    )
    sender_customer_reference = models.CharField(
        blank=True, max_length=250
    )
    reference = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now=False)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True)
    credited = models.BooleanField(default=False)

    STATUS_LOOKUP = {
        TRANSACTION_STATUS.PENDING:   {'owner__isnull': False, 'credited': False},
        TRANSACTION_STATUS.AVAILABLE: {'owner__isnull': True, 'credited': False},
        TRANSACTION_STATUS.CREDITED:  {'owner__isnull': False, 'credited': True}
    }

    objects = TransactionQuerySet.as_manager()

    def take(self, by_user):
        self.owner = by_user
        self.save()

        transaction_taken.send(
            sender=self.__class__, transaction=self, by_user=by_user
        )

    def release(self, by_user):
        self.owner = None
        self.save()

        transaction_released.send(
            sender=self.__class__, transaction=self, by_user=by_user
        )

    def credit(self, credited, by_user):
        self.credited = credited
        self.save()

        transaction_credited.send(
            sender=self.__class__, transaction=self, by_user=by_user
        )

    class Meta:
        ordering = ('received_at',)
        permissions = (
            ("view_transaction", "Can view transaction"),
            ("take_transaction", "Can take transaction"),
            ("release_transaction", "Can release transaction"),
            ("patch_credited_transaction", "Can patch credited transaction"),
        )


class Log(TimeStampedModel):
    transaction = models.ForeignKey(Transaction)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True)
    action = models.CharField(max_length=50, choices=LOG_ACTIONS)

    objects = LogManager()

    def __str__(self):
        return 'Transaction {id} {action} by {user}'.format(
            id=self.transaction.pk,
            user='<None>' if not self.user else self.user.username,
            action=self.action
        )


# SIGNALS

@receiver(post_save, sender=Transaction)
def transaction_created_receiver(sender, instance, created, **kwargs):
    if created:
        Log.objects.transaction_created(instance)


@receiver(transaction_taken)
def transaction_taken_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_taken(transaction, by_user)


@receiver(transaction_released)
def transaction_released_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_released(transaction, by_user)


@receiver(transaction_credited)
def transaction_credited_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_credited(transaction, by_user)
