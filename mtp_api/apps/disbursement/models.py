from django.conf import settings
from django.db import models
from django.dispatch import receiver
from model_utils.models import TimeStampedModel
from mtp_common.utils import format_currency

from disbursement import InvalidDisbursementStateException
from disbursement.constants import DisbursementResolution, DisbursementMethod, LogAction
from disbursement.managers import DisbursementManager, DisbursementQuerySet, LogManager
from disbursement.signals import (
    disbursement_confirmed, disbursement_created, disbursement_rejected,
    disbursement_sent, disbursement_edited
)
from prison.models import Prison


class Disbursement(TimeStampedModel):
    amount = models.PositiveIntegerField(db_index=True)
    prisoner_number = models.CharField(max_length=250, db_index=True)
    prisoner_name = models.CharField(max_length=250)
    prison = models.ForeignKey(Prison, on_delete=models.PROTECT)
    resolution = models.CharField(
        max_length=50,
        choices=DisbursementResolution.choices, default=DisbursementResolution.pending.value,
        db_index=True
    )
    method = models.CharField(max_length=50, choices=DisbursementMethod.choices, db_index=True)
    remittance_description = models.CharField(max_length=250, blank=True)

    # recipient details
    recipient_is_company = models.BooleanField(default=False)
    recipient_first_name = models.CharField(max_length=250, blank=True)
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

    nomis_transaction_id = models.CharField(max_length=50, blank=True, null=True)
    invoice_number = models.CharField(max_length=50, blank=True, null=True)

    recipient_profile = models.ForeignKey(
        'security.RecipientProfile', related_name='disbursements', blank=True, null=True,
        on_delete=models.SET_NULL
    )
    prisoner_profile = models.ForeignKey(
        'security.PrisonerProfile', related_name='disbursements', blank=True, null=True,
        on_delete=models.SET_NULL
    )

    objects = DisbursementManager.from_queryset(DisbursementQuerySet)()

    class Meta:
        ordering = ('id',)
        get_latest_by = 'created'
        indexes = [
            models.Index(fields=['created', 'id']),
            models.Index(fields=['-created', 'id']),
            models.Index(fields=['amount', 'id']),
            models.Index(fields=['-amount', 'id']),
            models.Index(fields=['prisoner_number', 'id']),
            models.Index(fields=['-prisoner_number', 'id']),
        ]

    @staticmethod
    def get_permitted_state(new_resolution):
        if new_resolution == DisbursementResolution.sent.value:
            return DisbursementResolution.confirmed.value
        elif new_resolution == DisbursementResolution.confirmed.value:
            return DisbursementResolution.preconfirmed.value
        elif new_resolution == DisbursementResolution.pending.value:
            return DisbursementResolution.preconfirmed.value
        else:
            return DisbursementResolution.pending.value

    def __str__(self):
        return 'Disbursement {id}, {amount} {prisoner} > {recipient}, {status}'.format(
            id=self.pk,
            amount=format_currency(self.amount, trim_empty_pence=True),
            prisoner=self.prisoner_number,
            recipient=self.recipient_name,
            status=self.resolution
        )

    def resolution_permitted(self, new_resolution):
        return self.resolution == self.get_permitted_state(new_resolution)

    @property
    def recipient_name(self):
        return '{} {}'.format(self.recipient_first_name, self.recipient_last_name).strip()

    @recipient_name.setter
    def recipient_name(self, _):
        pass

    @property
    def recipient_address(self):
        return ', '.join(
            filter(None, (self.address_line1, self.address_line2, self.city, self.postcode, self.country))
        )

    def reject(self, by_user):
        if self.resolution == DisbursementResolution.rejected.value:
            return
        if not self.resolution_permitted(DisbursementResolution.rejected.value):
            raise InvalidDisbursementStateException([self.id])
        self.resolution = DisbursementResolution.rejected.value
        self.save()
        disbursement_rejected.send(
            sender=Disbursement, disbursement=self, by_user=by_user)

    def preconfirm(self):
        if self.resolution == DisbursementResolution.preconfirmed.value:
            return
        if not self.resolution_permitted(DisbursementResolution.preconfirmed.value):
            raise InvalidDisbursementStateException([self.id])
        self.resolution = DisbursementResolution.preconfirmed.value
        self.save()

    def reset(self):
        if self.resolution == DisbursementResolution.pending.value:
            return
        if not self.resolution_permitted(DisbursementResolution.pending.value):
            raise InvalidDisbursementStateException([self.id])
        self.resolution = DisbursementResolution.pending.value
        self.save()

    def confirm(self, by_user, nomis_transaction_id=None):
        if self.resolution == DisbursementResolution.confirmed.value:
            return
        if not self.resolution_permitted(DisbursementResolution.confirmed.value):
            raise InvalidDisbursementStateException([self.id])
        self.resolution = DisbursementResolution.confirmed.value
        if nomis_transaction_id:
            self.nomis_transaction_id = nomis_transaction_id
        self.invoice_number = self._generate_invoice_number()
        self.save()
        disbursement_confirmed.send(
            sender=Disbursement, disbursement=self, by_user=by_user)

    def send(self, by_user):
        if self.resolution == DisbursementResolution.sent.value:
            return
        if not self.resolution_permitted(DisbursementResolution.sent.value):
            raise InvalidDisbursementStateException([self.id])
        self.resolution = DisbursementResolution.sent.value
        self.save()
        disbursement_sent.send(
            sender=Disbursement, disbursement=self, by_user=by_user)

    def _generate_invoice_number(self):
        return 'PMD%s' % (settings.INVOICE_NUMBER_BASE + self.id)


class Log(TimeStampedModel):
    disbursement = models.ForeignKey(Disbursement, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='disbursement_log'
    )
    action = models.CharField(max_length=50, choices=LogAction.choices)

    objects = LogManager()

    class Meta:
        ordering = ('id',)
        indexes = [
            models.Index(fields=['created']),
        ]

    def __str__(self):
        return 'Disbursement {id} {action} by {user}'.format(
            id=self.disbursement.pk,
            user='<None>' if not self.user else self.user.username,
            action=self.action
        )


class Comment(TimeStampedModel):
    disbursement = models.ForeignKey(
        Disbursement, on_delete=models.CASCADE, related_name='comments'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='disbursement_comments'
    )
    comment = models.TextField(max_length=3000)
    category = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        ordering = ('created',)

    def __str__(self):
        return 'Comment on disbursement {disbursement_id} by {user}'.format(
            disbursement_id=self.disbursement.pk,
            user='<None>' if not self.user else self.user.username,
        )


@receiver(disbursement_created)
def disbursement_created_receiver(disbursement, by_user, **kwargs):
    Log.objects.disbursements_created([disbursement], by_user)


@receiver(disbursement_edited)
def disbursement_edited_receiver(disbursement, by_user, **kwargs):
    Log.objects.disbursements_edited([disbursement], by_user)


@receiver(disbursement_rejected)
def disbursement_rejected_receiver(disbursement, by_user, **kwargs):
    Log.objects.disbursements_rejected([disbursement], by_user)


@receiver(disbursement_confirmed)
def disbursement_confirmed_receiver(disbursement, by_user, **kwargs):
    Log.objects.disbursements_confirmed([disbursement], by_user)


@receiver(disbursement_sent)
def disbursement_sent_receiver(disbursement, by_user, **kwargs):
    Log.objects.disbursements_sent([disbursement], by_user)
