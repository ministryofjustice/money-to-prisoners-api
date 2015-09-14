from django.db import models
from django.conf import settings
from django.dispatch import receiver

from model_utils.models import TimeStampedModel

from prison.models import Prison

from .constants import TRANSACTION_STATUS, LOG_ACTIONS
from .managers import TransactionQuerySet, LogManager
from .signals import transaction_created, transaction_locked, \
    transaction_unlocked, transaction_credited, transaction_refunded


class Transaction(TimeStampedModel):
    prison = models.ForeignKey(Prison, blank=True, null=True)

    prisoner_number = models.CharField(blank=True, max_length=250)
    prisoner_dob = models.DateField(blank=True, null=True)

    amount = models.PositiveIntegerField()

    # cannot be empty otherwise we can't send the money back
    sender_sort_code = models.CharField(max_length=50)
    sender_account_number = models.CharField(max_length=50)
    sender_name = models.CharField(max_length=250)

    # used by building societies to identify the account nr
    sender_roll_number = models.CharField(blank=True, max_length=50)

    # original reference
    reference = models.TextField(blank=True)

    received_at = models.DateTimeField(auto_now=False)

    # set when a transaction is locked and unset if it gets unlocked.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True)

    credited = models.BooleanField(default=False)

    refunded = models.BooleanField(default=False)

    STATUS_LOOKUP = {
        TRANSACTION_STATUS.LOCKED:
            {'owner__isnull': False, 'credited': False, 'refunded': False},
        TRANSACTION_STATUS.AVAILABLE:
            {'prison__isnull': False, 'owner__isnull': True, 'credited': False, 'refunded': False},
        TRANSACTION_STATUS.CREDITED:
            {'credited': True},
        TRANSACTION_STATUS.REFUNDED:
            {'refunded': True},
        TRANSACTION_STATUS.REFUND_PENDING:
            {'prison__isnull': True, 'owner__isnull': True, 'credited': False, 'refunded': False},
    }

    objects = TransactionQuerySet.as_manager()

    def lock(self, by_user):
        self.owner = by_user
        self.save()

        transaction_locked.send(
            sender=self.__class__, transaction=self, by_user=by_user
        )

    def unlock(self, by_user):
        self.owner = None
        self.save()

        transaction_unlocked.send(
            sender=self.__class__, transaction=self, by_user=by_user
        )

    def credit(self, credited, by_user):
        self.credited = credited
        self.save()

        transaction_credited.send(
            sender=self.__class__, transaction=self, by_user=by_user,
            credited=credited
        )

    class Meta:
        ordering = ('received_at',)
        permissions = (
            ("view_transaction", "Can view transaction"),
            ("view_bank_details_transaction", "Can view bank details of transaction"),
            ("lock_transaction", "Can lock transaction"),
            ("unlock_transaction", "Can unlock transaction"),
            ("patch_credited_transaction", "Can patch credited transaction"),
            ("patch_refunded_transaction", "Can patch refunded transaction"),
        )
        index_together = [
            ["prisoner_number", "prisoner_dob"],
        ]


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

@receiver(transaction_created)
def transaction_created_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_created(transaction, by_user)


@receiver(transaction_locked)
def transaction_locked_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_locked(transaction, by_user)


@receiver(transaction_unlocked)
def transaction_unlocked_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_unlocked(transaction, by_user)


@receiver(transaction_credited)
def transaction_credited_receiver(sender, transaction, by_user, credited=True, **kwargs):
    Log.objects.transaction_credited(transaction, by_user, credited=credited)


@receiver(transaction_refunded)
def transaction_refunded_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_refunded(transaction, by_user)
