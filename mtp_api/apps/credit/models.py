from datetime import timedelta
import logging

from django.conf import settings
from django.db import models
from django.db.models import Q, Max
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from model_utils.models import TimeStampedModel
from mtp_common.utils import format_currency

from credit.constants import CreditResolution, CreditStatus, CreditSource, LogAction
from credit.managers import (
    CompletedCreditManager,
    CreditingTimeManager,
    CreditManager,
    CreditQuerySet,
    LogManager,
    PrivateEstateBatchManager,
)
from credit.signals import (
    credit_created,
    credit_credited,
    credit_failed,
    credit_prisons_need_updating,
    credit_reconciled,
    credit_refunded,
    credit_reviewed,
    credit_set_manual,
)
from payment.constants import PaymentStatus
from prison.models import Prison, PrisonerLocation

logger = logging.getLogger('mtp')


class Credit(TimeStampedModel):
    amount = models.BigIntegerField(db_index=True)
    received_at = models.DateTimeField(auto_now=False, blank=True, null=True, db_index=True)

    prisoner_number = models.CharField(max_length=250, blank=True, null=True, db_index=True)
    prisoner_dob = models.DateField(blank=True, null=True)
    prisoner_name = models.CharField(blank=True, null=True, max_length=250)
    prison = models.ForeignKey(Prison, blank=True, null=True, on_delete=models.SET_NULL)

    resolution = models.CharField(max_length=50,
                                  choices=CreditResolution.choices, default=CreditResolution.pending.value,
                                  db_index=True)
    reconciled = models.BooleanField(default=False)
    reviewed = models.BooleanField(default=False)
    blocked = models.BooleanField(default=False)
    nomis_transaction_id = models.CharField(max_length=50, blank=True, null=True)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    sender_profile = models.ForeignKey('security.SenderProfile', related_name='credits', blank=True, null=True,
                                       on_delete=models.SET_NULL)
    is_counted_in_sender_profile_total = models.BooleanField(default=False)
    is_counted_in_prisoner_profile_total = models.BooleanField(default=False)
    prisoner_profile = models.ForeignKey('security.PrisonerProfile', related_name='credits', blank=True, null=True,
                                         on_delete=models.SET_NULL)

    private_estate_batch = models.ForeignKey('credit.PrivateEstateBatch', null=True, blank=True,
                                             on_delete=models.SET_NULL)

    objects = CompletedCreditManager.from_queryset(CreditQuerySet)()
    objects_all = CreditManager.from_queryset(CreditQuerySet)()

    # NB: there are matching boolean fields or properties on the model instance for each
    STATUS_LOOKUP = {
        CreditStatus.credit_pending.value: (
            Q(blocked=False) &
            Q(prison__isnull=False) &
            (Q(resolution=CreditResolution.pending) | Q(resolution=CreditResolution.manual))
        ),
        CreditStatus.credited.value: (
            Q(resolution=CreditResolution.credited)
        ),
        CreditStatus.refunded.value: (
            Q(resolution=CreditResolution.refunded)
        ),
        CreditStatus.refund_pending.value: (
            (Q(prison__isnull=True) | Q(blocked=True)) &
            Q(resolution=CreditResolution.pending) &
            (
                Q(transaction__isnull=True) |
                Q(transaction__incomplete_sender_info=False)
            )
        ),
        CreditStatus.failed.value: (
            Q(resolution=CreditResolution.failed)
        ),
    }

    class Meta:
        ordering = ('received_at', 'id',)
        get_latest_by = 'received_at'
        permissions = (
            ('view_any_credit', 'Can view any credit'),
            ('review_credit', 'Can review credit'),
            ('credit_credit', 'Can credit credit'),
        )
        indexes = [
            models.Index(fields=['prisoner_number', 'prisoner_dob']),
            models.Index(fields=['created']),
            models.Index(fields=['received_at', 'id']),
            models.Index(fields=['-received_at', 'id']),
            models.Index(fields=['amount', 'id']),
            models.Index(fields=['-amount', 'id']),
            models.Index(fields=['prisoner_number', 'id']),
            models.Index(fields=['-prisoner_number', 'id']),
            models.Index(fields=['owner', 'reconciled', 'resolution']),
        ]

    def __str__(self):
        return 'Credit {id}, {amount} {sender_name} > {prisoner_name}, {status}'.format(
            id=self.pk,
            amount=format_currency(self.amount, trim_empty_pence=True),
            sender_name=self.sender_name,
            prisoner_name=self.prisoner_name,
            status=self.status
        )

    def credit_prisoner(self, by_user, nomis_transaction_id=None):
        self.resolution = CreditResolution.credited.value
        self.owner = by_user
        if nomis_transaction_id:
            self.nomis_transaction_id = nomis_transaction_id
        self.save()

        credit_credited.send(
            sender=self.__class__, credit=self, by_user=by_user,
            credited=True
        )

    def reconcile(self, by_user):
        self.reconciled = True
        self.save()

        credit_reconciled.send(
            sender=self.__class__,
            credit=self,
            by_user=by_user
        )

    def attach_profiles(self, ignore_credit_resolution=False):
        from security.models import PrisonerProfile, SenderProfile

        assert ignore_credit_resolution or self.resolution != CreditResolution.failed.value, \
            'Do not attach profiles for failed credits outside of test setup'

        if not self.prisoner_profile and self.prison and self.prisoner_name:
            self.prisoner_profile = PrisonerProfile.objects.create_or_update_for_credit(self)
        if not self.sender_profile and self.has_enough_detail_for_sender_profile():
            self.sender_profile = SenderProfile.objects.create_or_update_for_credit(self)
        if self.resolution != CreditResolution.failed.value and self.prisoner_profile and self.sender_profile:
            # Annoyingly we still have to add this resolution clause for test setup, due to the fact that our test setup
            # does not go through the realistic state mutation properly, simply creating entities in their final state
            self.prisoner_profile.add_sender(self.sender_profile)

        if not self.prisoner_profile:
            logger.info(
                'Could not create PrisonerProfile for credit %(credit_instance)s '
                'because Credit lacked either a prison or prisoner name',
                {'credit_instance': self}
            )
        if not self.sender_profile:
            logger.info(
                'Could not create SenderProfile for credit %(credit_instance)s '
                'because Credit lacked necessary information',
                {'credit_instance': self}
            )

    def update_profiles_on_failed_state(self):
        # If a credit moves into failed after being linked to prisoner/sender profiles (at least one use case for this
        # , namely a payment being rejected by FIU) and there are now no completed credits linking prisoner profile
        # and sender profile, we remove the association
        if not self.sender_profile_id:
            return
        if self.prisoner_profile_id:
            sender_prisoner_valid_credit_count = Credit.objects.filter(
                sender_profile_id=self.sender_profile_id,
                prisoner_profile_id=self.prisoner_profile_id,
            ).exclude(
                id=self.id
            ).count()
            if sender_prisoner_valid_credit_count == 0:
                self.prisoner_profile.remove_sender(self.sender_profile)
        if self.prison_id:
            sender_prison_valid_credit_count = Credit.objects.filter(
                sender_profile_id=self.sender_profile_id,
                prison_id=self.prison_id,
            ).exclude(
                id=self.id
            ).count()
            if sender_prison_valid_credit_count == 0:
                self.sender_profile.remove_prison(self.prison)

    def should_check(self):
        if self.resolution != CreditResolution.initial.value:
            # it's too late once credits reach any other resolution
            return False
        if self.source != CreditSource.online.value:
            # checks only apply to debit card payments
            return False
        if self.payment.status != PaymentStatus.pending.value:
            # payment must be pending for checks to apply
            return False

        return self.has_enough_detail_for_sender_profile()

    def has_enough_detail_for_sender_profile(self):
        if self.source == CreditSource.online.value:
            return all(
                getattr(self.payment, field)
                for field in (
                    'email', 'cardholder_name',
                    'card_number_first_digits', 'card_number_last_digits', 'card_expiry_date',
                    'billing_address',
                )
            )
        elif self.source == CreditSource.bank_transfer.value:
            return all(
                getattr(self.transaction, field)
                for field in (
                    'sender_name', 'sender_sort_code', 'sender_account_number'
                )
            )

    @property
    def source(self):
        if hasattr(self, 'transaction'):
            return CreditSource.bank_transfer.value
        elif hasattr(self, 'payment'):
            return CreditSource.online.value
        else:
            return CreditSource.unknown.value

    @property
    def intended_recipient(self):
        if hasattr(self, 'payment'):
            return self.payment.recipient_name

    @property
    def credit_pending(self):
        return (
            self.prison is not None and
            (self.resolution == CreditResolution.pending.value or
             self.resolution == CreditResolution.manual.value) and
            not self.blocked
        )

    @property
    def credited(self):
        return self.resolution == CreditResolution.credited.value

    @property
    def refunded(self):
        return self.resolution == CreditResolution.refunded.value

    @property
    def failed(self):
        return self.resolution == CreditResolution.failed.value

    @property
    def refund_pending(self):
        return (
            (self.prison is None or self.blocked) and
            self.resolution == CreditResolution.pending.value and
            (
                not hasattr(self, 'transaction') or
                not self.transaction.incomplete_sender_info
            )
        )

    @property
    def status(self):
        if self.credit_pending:
            return CreditStatus.credit_pending.value
        elif self.credited:
            return CreditStatus.credited.value
        elif self.refund_pending:
            return CreditStatus.refund_pending.value
        elif self.refunded:
            return CreditStatus.refunded.value
        elif self.failed:
            return CreditStatus.failed.value

    @property
    def owner_name(self):
        return self.owner.get_full_name() if self.owner else None

    @property
    def sender_name(self):
        if hasattr(self, 'transaction'):
            if self.transaction.reference_in_sender_field:
                return self.transaction.reference
            else:
                return self.transaction.sender_name
        elif hasattr(self, 'payment'):
            return self.payment.cardholder_name

    @property
    def sender_sort_code(self):
        return self.transaction.sender_sort_code if hasattr(self, 'transaction') else None

    @property
    def sender_account_number(self):
        return self.transaction.sender_account_number if hasattr(self, 'transaction') else None

    @property
    def sender_roll_number(self):
        return self.transaction.sender_roll_number if hasattr(self, 'transaction') else None

    @property
    def sender_email(self):
        return self.payment.email if hasattr(self, 'payment') else None

    @property
    def card_number_first_digits(self):
        return self.payment.card_number_first_digits if hasattr(self, 'payment') else None

    @property
    def card_number_last_digits(self):
        return self.payment.card_number_last_digits if hasattr(self, 'payment') else None

    @property
    def card_expiry_date(self):
        return self.payment.card_expiry_date if hasattr(self, 'payment') else None

    @property
    def ip_address(self):
        return self.payment.ip_address if hasattr(self, 'payment') else None

    @property
    def billing_address(self):
        return self.payment.billing_address if hasattr(self, 'payment') else None

    @property
    def reconciliation_code(self):
        if hasattr(self, 'transaction'):
            return self.transaction.ref_code
        elif hasattr(self, 'payment'):
            return self.payment.ref_code

    @property
    def credited_at(self):
        if not self.resolution == CreditResolution.credited.value:
            return None
        return self.log_set.get_action_date(LogAction.credited)

    @property
    def refunded_at(self):
        if not self.resolution == CreditResolution.refunded.value:
            return None
        return self.log_set.get_action_date(LogAction.refunded)

    @property
    def set_manual_at(self):
        return self.log_set.get_action_date(LogAction.manual)

    @property
    def reconciled_at(self):
        if not self.reconciled:
            return None
        return self.log_set.get_action_date(LogAction.reconciled)

    @property
    def crediting_time(self):
        try:
            return self.creditingtime.crediting_time
        except CreditingTime.DoesNotExist:
            pass


class Log(TimeStampedModel):
    credit = models.ForeignKey(Credit, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='credit_log'
    )
    action = models.CharField(max_length=50, choices=LogAction.choices)

    objects = LogManager()

    class Meta:
        ordering = ('id',)
        indexes = [
            models.Index(fields=['created']),
        ]

    def __str__(self):
        return 'Credit {id} {action} by {user}'.format(
            id=self.credit.pk,
            user='<None>' if not self.user else self.user.username,
            action=self.action
        )


class CreditingTime(models.Model):
    credit = models.OneToOneField(Credit, primary_key=True, on_delete=models.CASCADE)
    crediting_time = models.DurationField(null=True)

    objects = CreditingTimeManager()

    def __str__(self):
        if self.crediting_time is None:
            return 'Credit %s not credited' % self.credit.pk
        return 'Credit %s credited in %s' % (self.credit.pk, self.crediting_time)


class Comment(TimeStampedModel):
    credit = models.ForeignKey(
        Credit, on_delete=models.CASCADE, related_name='comments'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='credit_comments'
    )
    comment = models.TextField(max_length=3000)

    def __str__(self):
        return 'Comment on credit {credit_id} by {user}'.format(
            credit_id=self.credit.pk,
            user='<None>' if not self.user else self.user.username,
        )


class ProcessingBatch(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    credits = models.ManyToManyField(Credit)

    class Meta:
        verbose_name_plural = 'processing batches'

    def __str__(self):
        return '%s %s' % (self.user.username, self.created)

    @property
    def expired(self):
        # indicates if the process has timed out
        now = timezone.now()
        if now - self.created < timedelta(minutes=2):
            return False
        last_updated = self.credits.all().aggregate(Max('modified'))['modified__max']
        if last_updated and (now - last_updated < timedelta(minutes=2)):
            return False
        return True


class PrivateEstateBatch(TimeStampedModel):
    date = models.DateField()
    prison = models.ForeignKey(Prison, on_delete=models.CASCADE)

    objects = PrivateEstateBatchManager()

    class Meta:
        ordering = ('date',)
        get_latest_by = 'date'
        verbose_name_plural = 'private estate batches'
        unique_together = (('date', 'prison'),)

    def __str__(self):
        return '%s %s' % (self.prison, self.date)

    @property
    def total_amount(self):
        return self.credit_set.aggregate(total=models.Sum('amount'))['total']


@receiver(post_save, sender=Credit, dispatch_uid='update_prison_for_credit')
def update_prison_for_credit(instance, created, **kwargs):
    if (created and
            instance.reconciled is False and
            (instance.resolution == CreditResolution.initial.value or
             instance.resolution == CreditResolution.pending.value) and
            instance.owner is None):
        try:
            location = PrisonerLocation.objects.get(
                prisoner_number=instance.prisoner_number,
                prisoner_dob=instance.prisoner_dob,
                active=True
            )
            instance.prisoner_name = location.prisoner_name
            instance.prison = location.prison
            instance.save()
        except PrisonerLocation.MultipleObjectsReturned:
            logger.error('Prisoner location is not unique for %(prisoner_number)s %(prisoner_dob)s', {
                'prisoner_number': instance.prisoner_number,
                'prisoner_dob': instance.prisoner_dob,
            })
        except PrisonerLocation.DoesNotExist:
            pass


@receiver(credit_created)
def credit_created_receiver(credit, by_user, **kwargs):
    Log.objects.credits_created([credit], by_user)


@receiver(credit_credited)
def credit_credited_receiver(credit, by_user, credited=True, **kwargs):
    Log.objects.credits_credited([credit], by_user, credited=credited)


@receiver(credit_refunded)
def credit_refunded_receiver(credit, by_user, **kwargs):
    Log.objects.credits_refunded([credit], by_user)


@receiver(credit_reconciled)
def credit_reconciled_receiver(credit, by_user, **kwargs):
    Log.objects.credits_reconciled([credit], by_user)


@receiver(credit_reviewed)
def credit_reviewed_receiver(credit, by_user, **kwargs):
    Log.objects.credits_reviewed([credit], by_user)


@receiver(credit_set_manual)
def credit_set_manual_receiver(credit, by_user, **kwargs):
    Log.objects.credits_set_manual([credit], by_user)


@receiver(credit_failed)
def credit_failed_receiver(credit, **kwargs):
    credit.update_profiles_on_failed_state()
    Log.objects.credits_failed([credit])


@receiver(credit_prisons_need_updating)
def update_credit_prisons(**kwargs):
    Credit.objects.update_prisons()
