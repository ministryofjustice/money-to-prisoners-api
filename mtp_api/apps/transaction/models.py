import warnings

from django.db import models
from django.conf import settings
from django.dispatch import receiver
from model_utils.models import TimeStampedModel

from prison.models import Prison
from .constants import (
    TRANSACTION_STATUS, LOG_ACTIONS, TRANSACTION_CATEGORY, TRANSACTION_SOURCE
)
from .managers import TransactionQuerySet, LogManager
from .signals import (
    transaction_created, transaction_locked,
    transaction_unlocked, transaction_credited, transaction_refunded,
    transaction_prisons_need_updating, transaction_reconciled,
)
from .utils import format_amount


class Transaction(TimeStampedModel):
    prison = models.ForeignKey(Prison, blank=True, null=True, on_delete=models.SET_NULL)

    prisoner_name = models.CharField(blank=True, null=True, max_length=250)
    prisoner_number = models.CharField(blank=True, null=True, max_length=250)
    prisoner_dob = models.DateField(blank=True, null=True)

    amount = models.PositiveIntegerField()
    category = models.CharField(max_length=50, choices=TRANSACTION_CATEGORY)
    source = models.CharField(max_length=50, choices=TRANSACTION_SOURCE)

    processor_type_code = models.CharField(max_length=12, blank=True, null=True)
    sender_sort_code = models.CharField(max_length=50, blank=True)
    sender_account_number = models.CharField(max_length=50, blank=True)
    sender_name = models.CharField(max_length=250, blank=True)

    # used by building societies to identify the account nr
    sender_roll_number = models.CharField(blank=True, max_length=50)

    # original reference
    reference = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now=False)

    # 6-digit reference code for reconciliation
    ref_code = models.CharField(max_length=12, null=True)

    # set when a transaction is locked and unset if it gets unlocked.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    credited = models.BooleanField(default=False)
    refunded = models.BooleanField(default=False)
    reconciled = models.BooleanField(default=False)
    incomplete_sender_info = models.BooleanField(default=False)

    # NB: there are matching boolean fields or properties on the model instance for each
    STATUS_LOOKUP = {
        TRANSACTION_STATUS.LOCKED: {
            'owner__isnull': False,
            'credited': False,
            'refunded': False,
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source__in': [
                TRANSACTION_SOURCE.BANK_TRANSFER,
                TRANSACTION_SOURCE.ONLINE
            ]
        },
        TRANSACTION_STATUS.AVAILABLE: {
            'prison__isnull': False,
            'owner__isnull': True,
            'credited': False,
            'refunded': False,
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source__in': [
                TRANSACTION_SOURCE.BANK_TRANSFER,
                TRANSACTION_SOURCE.ONLINE
            ]
        },
        TRANSACTION_STATUS.CREDITED: {
            'credited': True,
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source__in': [
                TRANSACTION_SOURCE.BANK_TRANSFER,
                TRANSACTION_SOURCE.ONLINE
            ]
        },
        TRANSACTION_STATUS.REFUNDED: {
            'refunded': True,
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source': TRANSACTION_SOURCE.BANK_TRANSFER
        },
        TRANSACTION_STATUS.REFUND_PENDING: {
            'prison__isnull': True,
            'owner__isnull': True,
            'credited': False,
            'refunded': False,
            'incomplete_sender_info': False,
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source': TRANSACTION_SOURCE.BANK_TRANSFER
        },
        TRANSACTION_STATUS.UNIDENTIFIED: {
            'prison__isnull': True,
            'incomplete_sender_info': True,
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source': TRANSACTION_SOURCE.BANK_TRANSFER
        },
        TRANSACTION_STATUS.ANOMALOUS: {
            'category': TRANSACTION_CATEGORY.CREDIT,
            'source': TRANSACTION_SOURCE.ADMINISTRATIVE
        }
    }

    objects = TransactionQuerySet.as_manager()

    class Meta:
        ordering = ('received_at',)
        permissions = (
            ('view_transaction', 'Can view transaction'),
            ('view_bank_details_transaction', 'Can view bank details of transaction'),
            ('lock_transaction', 'Can lock transaction'),
            ('unlock_transaction', 'Can unlock transaction'),
            ('patch_credited_transaction', 'Can patch credited transaction'),
            ('patch_processed_transaction', 'Can patch processed transaction'),
        )
        index_together = (
            ('prisoner_number', 'prisoner_dob'),
        )

    def __str__(self):
        return 'Transaction {id}, {amount} {sender_name} > {prisoner_name}'.format(
            id=self.pk,
            amount=format_amount(self.amount, True),
            sender_name=self.sender_name,
            prisoner_name=self.prisoner_name,
        )

    @property
    def available(self):
        return (self.prison is not None and self.owner is None and
                not (self.credited or self.refunded) and
                self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source in [
                    TRANSACTION_SOURCE.BANK_TRANSFER,
                    TRANSACTION_SOURCE.ONLINE
                ])

    @property
    def locked(self):
        return (self.owner is not None and
                not (self.credited or self.refunded) and
                self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source in [
                    TRANSACTION_SOURCE.BANK_TRANSFER,
                    TRANSACTION_SOURCE.ONLINE
                ])

    @property
    def status_credited(self):
        return (self.credited and self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source in [
                    TRANSACTION_SOURCE.BANK_TRANSFER,
                    TRANSACTION_SOURCE.ONLINE
                ])

    @property
    def status_refunded(self):
        return (self.refunded and self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source == TRANSACTION_SOURCE.BANK_TRANSFER)

    @property
    def refund_pending(self):
        return (self.prison is None and self.owner is None and
                not (self.credited or self.refunded) and
                not self.incomplete_sender_info and
                self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source == TRANSACTION_SOURCE.BANK_TRANSFER)

    @property
    def unidentified(self):
        return (self.prison is None and
                self.incomplete_sender_info and
                self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source == TRANSACTION_SOURCE.BANK_TRANSFER)

    @property
    def anomalous(self):
        return (self.category == TRANSACTION_CATEGORY.CREDIT and
                self.source == TRANSACTION_SOURCE.ADMINISTRATIVE)

    @property
    def status(self):
        if self.available:
            return TRANSACTION_STATUS.AVAILABLE
        elif self.locked:
            return TRANSACTION_STATUS.LOCKED
        elif self.status_credited:
            return TRANSACTION_STATUS.CREDITED
        elif self.status_refunded:
            return TRANSACTION_STATUS.REFUNDED
        elif self.refund_pending:
            return TRANSACTION_STATUS.REFUND_PENDING
        elif self.unidentified:
            return TRANSACTION_STATUS.UNIDENTIFIED
        elif self.anomalous:
            return TRANSACTION_STATUS.ANOMALOUS

    @property
    def reconcilable(self):
        return self.status in [
            TRANSACTION_STATUS.AVAILABLE, TRANSACTION_STATUS.LOCKED,
            TRANSACTION_STATUS.CREDITED, TRANSACTION_STATUS.REFUND_PENDING,
            TRANSACTION_STATUS.REFUNDED
        ]

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

    @property
    def owner_name(self):
        return self.owner.get_full_name() if self.owner else None

    @property
    def credited_at(self):
        if not self.credited:
            return None
        log_action = self.log_set.filter(action=LOG_ACTIONS.CREDITED) \
            .order_by('-created').first()
        if not log_action:
            warnings.warn('Transaction model %s is missing a credited log' % self.pk)
            return None
        return log_action.created

    @property
    def refunded_at(self):
        if not self.refunded:
            return None
        log_action = self.log_set.filter(action=LOG_ACTIONS.REFUNDED) \
            .order_by('-created').first()
        if not log_action:
            warnings.warn('Transaction model %s is missing a refunded log' % self.pk)
            return None
        return log_action.created

    @property
    def reconciled_at(self):
        if not self.reconciled:
            return None
        log_action = self.log_set.filter(action=LOG_ACTIONS.RECONCILED) \
            .order_by('-created').first()
        if not log_action:
            warnings.warn('Transaction model %s is missing a reconciled log' % self.pk)
            return None
        return log_action.created

    @property
    def locked_at(self):
        if not self.locked:
            return None
        log_action = self.log_set.filter(action=LOG_ACTIONS.LOCKED) \
            .order_by('-created').first()
        if not log_action:
            warnings.warn('Transaction model %s is missing a locked log' % self.pk)
            return None
        return log_action.created


class Log(TimeStampedModel):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
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


@receiver(transaction_reconciled)
def transaction_reconciled_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_reconciled(transaction, by_user)


@receiver(transaction_prisons_need_updating)
def update_transaction_prisons(*args, **kwargs):
    Transaction.objects.update_prisons()
