import warnings

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from model_utils.models import TimeStampedModel

from prison.models import Prison, PrisonerLocation
from transaction.utils import format_amount
from .constants import LOG_ACTIONS, CREDIT_RESOLUTION, CREDIT_STATUS
from .managers import CreditManager, CreditQuerySet, LogManager
from .signals import (
    credit_created, credit_locked, credit_unlocked, credit_credited,
    credit_refunded, credit_reconciled, credit_prisons_need_updating
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

    objects = CreditManager.from_queryset(CreditQuerySet)()

    STATUS_LOOKUP = {
        CREDIT_STATUS.LOCKED: {
            'owner__isnull': False,
            'resolution': CREDIT_RESOLUTION.PENDING,
        },
        CREDIT_STATUS.AVAILABLE: {
            'prison__isnull': False,
            'owner__isnull': True,
            'resolution': CREDIT_RESOLUTION.PENDING,
        },
        CREDIT_STATUS.CREDITED: {
            'resolution': CREDIT_RESOLUTION.CREDITED,
        },
        CREDIT_STATUS.REFUNDED: {
            'resolution': CREDIT_RESOLUTION.REFUNDED,
        },
        CREDIT_STATUS.REFUND_PENDING: {
            'prison__isnull': True,
            'resolution': CREDIT_RESOLUTION.PENDING,
        },
    }

    def __str__(self):
        return 'Credit {id}, {amount} {sender_name} > {prisoner_name}, {status}'.format(
            id=self.pk,
            amount=format_amount(self.amount, True),
            sender_name=self.sender,
            prisoner_name=self.prisoner_name,
            status=self.status
        )

    def lock(self, by_user):
        self.owner = by_user
        self.save()

        credit_locked.send(
            sender=self.__class__, credit=self, by_user=by_user
        )

    def unlock(self, by_user):
        self.owner = None
        self.save()

        credit_unlocked.send(
            sender=self.__class__, credit=self, by_user=by_user
        )

    def credit_prisoner(self, credited, by_user):
        if credited:
            self.resolution = CREDIT_RESOLUTION.CREDITED
        else:
            self.resolution = CREDIT_RESOLUTION.PENDING
        self.save()

        credit_credited.send(
            sender=self.__class__, credit=self, by_user=by_user,
            credited=credited
        )

    def reconcile(self, by_user):
        self.reconciled = True
        self.save()

        credit_reconciled.send(
            sender=self.__class__,
            credit=self,
            by_user=by_user
        )

    @property
    def available(self):
        return (
            self.owner is None and self.prison is not None and
            self.resolution == CREDIT_RESOLUTION.PENDING
        )

    @property
    def locked(self):
        return (
            self.owner is not None and self.resolution == CREDIT_RESOLUTION.PENDING
        )

    @property
    def credited(self):
        return self.resolution == CREDIT_RESOLUTION.CREDITED

    @property
    def refunded(self):
        return self.resolution == CREDIT_RESOLUTION.REFUNDED

    @property
    def refund_pending(self):
        return (
            self.prison is None and self.resolution == CREDIT_RESOLUTION.PENDING
        )

    @property
    def status(self):
        if self.available:
            return CREDIT_STATUS.AVAILABLE
        elif self.locked:
            return CREDIT_STATUS.LOCKED
        elif self.credited:
            return CREDIT_STATUS.CREDITED
        elif self.refund_pending:
            return CREDIT_STATUS.REFUND_PENDING
        elif self.refunded:
            return CREDIT_STATUS.REFUNDED

    @property
    def owner_name(self):
        return self.owner.get_full_name() if self.owner else None

    @property
    def sender(self):
        return self.transaction.sender_name if hasattr(self, 'transaction') else None

    @property
    def credited_at(self):
        if not self.resolution == CREDIT_RESOLUTION.CREDITED:
            return None
        log_action = self.log_set.filter(action=LOG_ACTIONS.CREDITED) \
            .order_by('-created').first()
        if not log_action:
            warnings.warn('Credit model %s is missing a credited log' % self.pk)
            return None
        return log_action.created

    @property
    def refunded_at(self):
        if not self.resolution == CREDIT_RESOLUTION.REFUNDED:
            return None
        log_action = self.log_set.filter(action=LOG_ACTIONS.REFUNDED) \
            .order_by('-created').first()
        if not log_action:
            warnings.warn('Credit model %s is missing a refunded log' % self.pk)
            return None
        return log_action.created

    @property
    def reconciled_at(self):
        if not self.reconciled:
            return None
        log_action = self.log_set.filter(action=LOG_ACTIONS.RECONCILED) \
            .order_by('-created').first()
        if not log_action:
            warnings.warn('Credit model %s is missing a reconciled log' % self.pk)
            return None
        return log_action.created

    @property
    def locked_at(self):
        if not self.locked:
            return None
        log_action = self.log_set.filter(action=LOG_ACTIONS.LOCKED) \
            .order_by('-created').first()
        if not log_action:
            warnings.warn('Credit model %s is missing a locked log' % self.pk)
            return None
        return log_action.created


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


@receiver(credit_prisons_need_updating)
def update_credit_prisons(*args, **kwargs):
    Credit.objects.update_prisons()
