from functools import reduce
from itertools import chain

from django.db import models
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from core.models import ScheduledCommand
from prison.models import Prison
from .managers import PrisonProfileManager
from .signals import prisoner_profile_current_prisons_need_updating


class SenderProfile(TimeStampedModel):
    credit_count = models.IntegerField(default=0)
    credit_total = models.IntegerField(default=0)

    class Meta:
        permissions = (
            ('view_senderprofile', 'Can view sender profile'),
        )

    @property
    def credit_filters(self):
        return (
            reduce(
                lambda x, y: x | y,
                chain(
                    (
                        models.Q(transaction__sender_name=d.sender_name) &
                        models.Q(transaction__sender_sort_code=d.sender_sort_code) &
                        models.Q(transaction__sender_account_number=d.sender_account_number) &
                        models.Q(transaction__sender_roll_number=d.sender_roll_number)
                        for d in self.bank_transfer_details.all()
                    ),
                    (
                        models.Q(payment__card_number_last_digits=d.card_number_last_digits) &
                        models.Q(payment__card_expiry_date=d.card_expiry_date)
                        for d in self.debit_card_details.all()
                    )
                ),
                models.Q(pk=None)
            )
        )

    def __str__(self):
        return 'Sender %s' % self.id

    def get_sender_names(self):
        yield from (details.sender_name for details in self.bank_transfer_details.all())
        for details in self.debit_card_details.all():
            yield from (cardholder.name for cardholder in details.cardholder_names.all())

    def get_sorted_sender_names(self):
        return sorted(set(filter(lambda name: (name or '').strip() or _('(Unknown)'), self.get_sender_names())))


class BankTransferSenderDetails(TimeStampedModel):
    sender_name = models.CharField(max_length=250, blank=True)
    sender_sort_code = models.CharField(max_length=50, blank=True)
    sender_account_number = models.CharField(max_length=50, blank=True)
    sender_roll_number = models.CharField(max_length=50, blank=True)
    sender = models.ForeignKey(
        SenderProfile, on_delete=models.CASCADE, related_name='bank_transfer_details'
    )

    class Meta:
        verbose_name_plural = 'bank transfer sender details'
        unique_together = (
            ('sender_name', 'sender_sort_code', 'sender_account_number', 'sender_roll_number'),
        )

    def __str__(self):
        return self.sender_name


class DebitCardSenderDetails(TimeStampedModel):
    card_number_last_digits = models.CharField(max_length=4, blank=True, null=True)
    card_expiry_date = models.CharField(max_length=5, blank=True, null=True)
    sender = models.ForeignKey(
        SenderProfile, on_delete=models.CASCADE, related_name='debit_card_details'
    )

    class Meta:
        verbose_name_plural = 'debit card sender details'
        unique_together = (
            ('card_number_last_digits', 'card_expiry_date',),
        )

    def __str__(self):
        return '%s %s' % (self.card_number_last_digits, self.card_expiry_date)


class CardholderName(models.Model):
    name = models.CharField(max_length=250)
    debit_card_sender_details = models.ForeignKey(
        DebitCardSenderDetails, on_delete=models.CASCADE,
        related_name='cardholder_names', related_query_name='cardholder_name'
    )

    def __str__(self):
        return self.name


class SenderEmail(models.Model):
    email = models.CharField(max_length=250)
    debit_card_sender_details = models.ForeignKey(
        DebitCardSenderDetails, on_delete=models.CASCADE,
        related_name='sender_emails', related_query_name='sender_email'
    )

    def __str__(self):
        return self.email


class PrisonerProfile(TimeStampedModel):
    prisoner_name = models.CharField(max_length=250)
    prisoner_number = models.CharField(max_length=250)
    prisoner_dob = models.DateField()
    credit_count = models.IntegerField(default=0)
    credit_total = models.IntegerField(default=0)
    current_prison = models.ForeignKey(
        Prison, on_delete=models.SET_NULL, null=True, related_name='current_prisoners'
    )

    prisons = models.ManyToManyField(Prison, related_name='historic_prisoners')
    senders = models.ManyToManyField(SenderProfile, related_name='prisoners')

    objects = PrisonProfileManager()

    @property
    def credit_filters(self):
        return (
            models.Q(prisoner_name=self.prisoner_name) &
            models.Q(prisoner_dob=self.prisoner_dob)
        )

    class Meta:
        permissions = (
            ('view_prisonerprofile', 'Can view prisoner profile'),
        )

    def __str__(self):
        return self.prisoner_number


class SecurityDataUpdate(models.Model):
    max_credit_pk = models.IntegerField()

    class Meta:
        ordering = ('-max_credit_pk',)
        get_latest_by = 'max_credit_pk'

    def __str__(self):
        return 'Last security update for credit %s' % self.max_credit_pk


@receiver(prisoner_profile_current_prisons_need_updating)
def update_current_prisons(*args, **kwargs):
    job = ScheduledCommand(
        name='update_current_prisons',
        arg_string='',
        cron_entry='*/10 * * * *',
        delete_after_next=True
    )
    job.save()
