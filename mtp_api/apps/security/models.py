from functools import reduce
from itertools import chain

from django.contrib.auth.models import User
from django.db import models
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from core.models import ScheduledCommand
from credit.models import Credit
from disbursement.models import Disbursement
from prison.models import Prison
from .managers import PrisonProfileManager
from .signals import prisoner_profile_current_prisons_need_updating


class SenderProfile(TimeStampedModel):
    credit_count = models.IntegerField(default=0)
    credit_total = models.IntegerField(default=0)

    prisons = models.ManyToManyField(Prison, related_name='senders')

    class Meta:
        ordering = ('created',)
        permissions = (
            ('view_senderprofile', 'Can view sender profile'),
        )

    def __str__(self):
        return 'Sender %s' % self.id

    @property
    def credit_filters(self):
        try:
            return reduce(
                models.Q.__or__,
                chain(
                    (
                        models.Q(
                            transaction__sender_name=d.sender_name,
                            transaction__sender_sort_code=d.sender_bank_account.sort_code,
                            transaction__sender_account_number=d.sender_bank_account.account_number,
                            transaction__sender_roll_number=d.sender_bank_account.roll_number
                        )
                        for d in self.bank_transfer_details.all()
                    ),
                    (
                        models.Q(
                            payment__card_number_last_digits=d.card_number_last_digits,
                            payment__card_expiry_date=d.card_expiry_date
                        )
                        for d in self.debit_card_details.all()
                    )
                )
            )
        except TypeError:
            return models.Q(pk=None)

    def update_totals(self):
        queryset = Credit.objects.filter(self.credit_filters)
        totals = queryset.aggregate(credit_count=models.Count('pk'),
                                    credit_total=models.Sum('amount'))
        self.credit_count = totals.get('credit_count') or 0
        self.credit_total = totals.get('credit_total') or 0
        self.save()

    def get_sender_names(self):
        yield from (details.sender_name for details in self.bank_transfer_details.all())
        for details in self.debit_card_details.all():
            yield from (cardholder.name for cardholder in details.cardholder_names.all())

    def get_sorted_sender_names(self):
        return sorted(set(filter(lambda name: (name or '').strip() or _('(Unknown)'), self.get_sender_names())))


class BankAccount(models.Model):
    sort_code = models.CharField(max_length=50, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    roll_number = models.CharField(max_length=50, blank=True)

    class Meta:
        unique_together = (
            ('sort_code', 'account_number', 'roll_number'),
        )


class BankTransferSenderDetails(TimeStampedModel):
    sender_name = models.CharField(max_length=250, blank=True)
    sender_bank_account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='senders'
    )
    sender = models.ForeignKey(
        SenderProfile, on_delete=models.CASCADE, related_name='bank_transfer_details'
    )

    class Meta:
        ordering = ('created',)
        verbose_name_plural = 'bank transfer sender details'

    def __str__(self):
        return self.sender_name


class DebitCardSenderDetails(TimeStampedModel):
    card_number_last_digits = models.CharField(max_length=4, blank=True, null=True, db_index=True)
    card_expiry_date = models.CharField(max_length=5, blank=True, null=True)
    postcode = models.CharField(max_length=250, blank=True, null=True, db_index=True)
    sender = models.ForeignKey(
        SenderProfile, on_delete=models.CASCADE, related_name='debit_card_details'
    )

    class Meta:
        ordering = ('created',)
        verbose_name_plural = 'debit card sender details'
        unique_together = (
            ('card_number_last_digits', 'card_expiry_date', 'postcode',),
        )

    def __str__(self):
        return '%s %s' % (self.card_number_last_digits, self.card_expiry_date)


class CardholderName(models.Model):
    name = models.CharField(max_length=250)
    debit_card_sender_details = models.ForeignKey(
        DebitCardSenderDetails, on_delete=models.CASCADE,
        related_name='cardholder_names', related_query_name='cardholder_name'
    )

    class Meta:
        ordering = ('pk',)

    def __str__(self):
        return self.name


class SenderEmail(models.Model):
    email = models.CharField(max_length=250)
    debit_card_sender_details = models.ForeignKey(
        DebitCardSenderDetails, on_delete=models.CASCADE,
        related_name='sender_emails', related_query_name='sender_email'
    )

    class Meta:
        ordering = ('pk',)

    def __str__(self):
        return self.email


class PrisonerProfile(TimeStampedModel):
    prisoner_name = models.CharField(max_length=250)
    prisoner_number = models.CharField(max_length=250, db_index=True)
    single_offender_id = models.UUIDField(blank=True, null=True)
    prisoner_dob = models.DateField()
    credit_count = models.IntegerField(default=0)
    credit_total = models.IntegerField(default=0)
    current_prison = models.ForeignKey(
        Prison, on_delete=models.SET_NULL, null=True, related_name='current_prisoners'
    )

    prisons = models.ManyToManyField(Prison, related_name='historic_prisoners')
    senders = models.ManyToManyField(SenderProfile, related_name='prisoners')

    objects = PrisonProfileManager()

    class Meta:
        ordering = ('created',)
        permissions = (
            ('view_prisonerprofile', 'Can view prisoner profile'),
        )
        unique_together = (
            ('prisoner_number', 'prisoner_dob',),
        )

    def __str__(self):
        return self.prisoner_number

    @property
    def credit_filters(self):
        return models.Q(prisoner_name=self.prisoner_name, prisoner_dob=self.prisoner_dob)

    def update_totals(self):
        queryset = Credit.objects.filter(self.credit_filters)
        totals = queryset.aggregate(credit_count=models.Count('pk'),
                                    credit_total=models.Sum('amount'))
        self.credit_count = totals.get('credit_count') or 0
        self.credit_total = totals.get('credit_total') or 0
        self.save()


class ProvidedPrisonerName(models.Model):
    name = models.CharField(max_length=250)
    prisoner = models.ForeignKey(
        PrisonerProfile, on_delete=models.CASCADE,
        related_name='provided_names', related_query_name='provided_name',
    )

    class Meta:
        ordering = ('pk',)

    def __str__(self):
        return self.name


class RecipientProfile(TimeStampedModel):
    disbursement_count = models.IntegerField(default=0)
    disbursement_total = models.IntegerField(default=0)

    class Meta:
        ordering = ('created',)
        permissions = (
            ('view_recipientprofile', 'Can view recipient profile'),
        )

    def __str__(self):
        return 'Recipient %s' % self.id

    @property
    def disbursement_filters(self):
        try:
            return reduce(
                models.Q.__or__,
                chain(
                    (
                        models.Q(
                            sort_code=d.recipient_bank_account.sort_code,
                            account_number=d.recipient_bank_account.account_number,
                            roll_number=d.recipient_bank_account.roll_number
                        )
                        for d in self.bank_transfer_details.all()
                    )
                )
            )
        except TypeError:
            return models.Q(pk=None)

    def update_totals(self):
        queryset = Disbursement.objects.filter(self.disbursement_filters)
        totals = queryset.aggregate(disbursement_count=models.Count('pk'),
                                    disbursement_total=models.Sum('amount'))
        self.disbursement_count = totals.get('disbursement_count') or 0
        self.disbursement_total = totals.get('disbursement_total') or 0
        self.save()


class BankTransferRecipientDetails(TimeStampedModel):
    recipient_bank_account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='recipients'
    )
    recipient = models.ForeignKey(
        RecipientProfile, on_delete=models.CASCADE, related_name='bank_transfer_details'
    )

    class Meta:
        ordering = ('created',)
        verbose_name_plural = 'bank transfer recipient details'


class SavedSearch(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.CharField(max_length=255)
    endpoint = models.CharField(max_length=255)
    last_result_count = models.IntegerField(default=0)
    site_url = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        ordering = ('created',)

    def __str__(self):
        return '{user}: {title}'.format(user=self.user.username, title=self.description)


class SearchFilter(models.Model):
    field = models.CharField(max_length=255)
    value = models.CharField(max_length=255)
    saved_search = models.ForeignKey(
        SavedSearch, on_delete=models.CASCADE, related_name='filters'
    )

    def __str__(self):
        return '{field}={value}'.format(field=self.field, value=self.value)


@receiver(prisoner_profile_current_prisons_need_updating)
def update_current_prisons(*args, **kwargs):
    job = ScheduledCommand(
        name='update_current_prisons',
        arg_string='',
        cron_entry='*/10 * * * *',
        delete_after_next=True
    )
    job.save()
