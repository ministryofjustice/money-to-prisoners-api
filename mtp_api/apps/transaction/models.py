from datetime import timedelta
import warnings

from django.db import models
from django.conf import settings
from django.dispatch import receiver
from model_utils.models import TimeStampedModel

from prison.models import Prison
from .constants import (
    TRANSACTION_STATUS, LOG_ACTIONS, TRANSACTION_CATEGORY, PAYMENT_OUTCOME
)
from .managers import TransactionQuerySet, LogManager
from .signals import (
    transaction_created, transaction_locked,
    transaction_unlocked, transaction_credited, transaction_refunded,
    transaction_prisons_need_updating, transaction_reconciled,
    transaction_payment_taken, transaction_payment_failed
)


class Transaction(TimeStampedModel):
    prison = models.ForeignKey(Prison, blank=True, null=True)

    prisoner_name = models.CharField(blank=True, null=True, max_length=250)
    prisoner_number = models.CharField(blank=True, null=True, max_length=250)
    prisoner_dob = models.DateField(blank=True, null=True)

    amount = models.PositiveIntegerField()
    category = models.CharField(max_length=50, choices=TRANSACTION_CATEGORY)

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
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True)

    credited = models.BooleanField(default=False)
    refunded = models.BooleanField(default=False)
    reconciled = models.BooleanField(default=False)

    payment_outcome = models.CharField(max_length=50, choices=PAYMENT_OUTCOME,
                                       default=PAYMENT_OUTCOME.TAKEN)

    # NB: there are matching boolean fields or properties on the model instance for each
    STATUS_LOOKUP = {
        TRANSACTION_STATUS.LOCKED: {
            'owner__isnull': False,
            'credited': False,
            'refunded': False,
            'category__in': [
                TRANSACTION_CATEGORY.CREDIT,
                TRANSACTION_CATEGORY.ONLINE_CREDIT
            ],
        },
        TRANSACTION_STATUS.AVAILABLE: {
            'prison__isnull': False,
            'owner__isnull': True,
            'credited': False,
            'refunded': False,
            'category__in': [
                TRANSACTION_CATEGORY.CREDIT,
                TRANSACTION_CATEGORY.ONLINE_CREDIT
            ],
            'payment_outcome': PAYMENT_OUTCOME.TAKEN
        },
        TRANSACTION_STATUS.CREDITED: {
            'credited': True,
            'category__in': [
                TRANSACTION_CATEGORY.CREDIT,
                TRANSACTION_CATEGORY.ONLINE_CREDIT
            ],
        },
        TRANSACTION_STATUS.REFUNDED: {
            'refunded': True,
            'category': TRANSACTION_CATEGORY.CREDIT
        },
        TRANSACTION_STATUS.REFUND_PENDING: {
            'prison__isnull': True,
            'owner__isnull': True,
            'credited': False,
            'refunded': False,
            'payment_outcome': PAYMENT_OUTCOME.TAKEN,
            'category': TRANSACTION_CATEGORY.CREDIT
        },
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
            ('patch_completed_transaction', 'Can patch completed transaction'),
        )
        index_together = (
            ('prisoner_number', 'prisoner_dob'),
        )

    def __str__(self):
        return 'Transaction {id}, £{amount:.2f} {sender_name} > {prisoner_name}'.format(
            id=self.pk,
            amount=self.amount / 100,
            sender_name=self.sender_name,
            prisoner_name=self.prisoner_name,
        )

    @property
    def available(self):
        return (self.prison is not None and self.owner is None and
                not (self.credited or self.refunded) and
                self.category == TRANSACTION_CATEGORY.CREDIT)

    @property
    def locked(self):
        return (self.owner is not None and
                not (self.credited or self.refunded) and
                self.category == TRANSACTION_CATEGORY.CREDIT)

    @property
    def refund_pending(self):
        return (self.prison is None and self.owner is None and
                not (self.credited or self.refunded) and
                self.category == TRANSACTION_CATEGORY.CREDIT)

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

    def populate_ref_code(self):
        if self.category == TRANSACTION_CATEGORY.CREDIT:
            code_date = self.received_at.replace(hour=0, minute=0,
                                                 second=0, microsecond=0)
            qs = Transaction.objects.filter(
                received_at__gte=code_date,
                received_at__lt=code_date + timedelta(days=1),
                ref_code__isnull=False,
                category=TRANSACTION_CATEGORY.CREDIT
            ).aggregate(models.Max('ref_code'))

            if qs and qs.get('ref_code__max'):
                self.ref_code = int(qs['ref_code__max']) + 1
            else:
                self.ref_code = settings.REF_CODE_BASE
            self.save()


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
    transaction.populate_ref_code()


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


@receiver(transaction_payment_taken)
def transaction_payment_taken_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_payment_taken(transaction, by_user)


@receiver(transaction_payment_failed)
def transaction_payment_failed_receiver(sender, transaction, by_user, **kwargs):
    Log.objects.transaction_payment_failed(transaction, by_user)


@receiver(transaction_prisons_need_updating)
def update_transaction_prisons(*args, **kwargs):
    Transaction.objects.update_prisons()
