from django.contrib.auth.models import User
from django.db import models
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from core.models import ScheduledCommand
from prison.models import Prison
from .managers import PrisonerProfileManager, SenderProfileManager, RecipientProfileManager
from .signals import prisoner_profile_current_prisons_need_updating


class SenderProfile(TimeStampedModel):
    credit_count = models.BigIntegerField(default=0)
    credit_total = models.BigIntegerField(default=0)

    prisons = models.ManyToManyField(Prison, related_name='senders')

    objects = SenderProfileManager()

    class Meta:
        ordering = ('created',)
        permissions = (
            ('view_senderprofile', 'Can view sender profile'),
        )
        indexes = [
            models.Index(fields=['credit_count']),
            models.Index(fields=['credit_total']),
        ]

    def __str__(self):
        return 'Sender %s' % self.id

    def get_sender_names(self):
        yield from (details.sender_name for details in self.bank_transfer_details.all())
        for details in self.debit_card_details.all():
            yield from (cardholder.name for cardholder in details.cardholder_names.all())

    def get_sorted_sender_names(self):
        return sorted(set(filter(lambda name: (name or '').strip() or _('(Unknown)'), self.get_sender_names())))

    def get_monitoring_users(self):
        details = self.debit_card_details.first()
        if details:
            return details.monitoring_users
        details = self.bank_transfer_details.first()
        if details:
            return details.sender_bank_account.monitoring_users
        return User.objects.none()


class BankAccount(models.Model):
    sort_code = models.CharField(max_length=50, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    roll_number = models.CharField(max_length=50, blank=True)

    monitoring_users = models.ManyToManyField(
        User, related_name='monitored_bank_accounts'
    )

    class Meta:
        unique_together = (
            ('sort_code', 'account_number', 'roll_number'),
        )

    def __str__(self):
        return (
            'BankAccount{sort_code=%s, account_number=%s, roll_number=%s}' %
            (self.sort_code, self.account_number, self.roll_number or 'n/a')
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

    monitoring_users = models.ManyToManyField(
        User, related_name='monitored_debit_cards'
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


class RecipientProfile(TimeStampedModel):
    disbursement_count = models.BigIntegerField(default=0)
    disbursement_total = models.BigIntegerField(default=0)

    prisons = models.ManyToManyField(Prison, related_name='recipients')

    objects = RecipientProfileManager()

    class Meta:
        ordering = ('created',)
        permissions = (
            ('view_recipientprofile', 'Can view recipient profile'),
        )
        indexes = [
            models.Index(fields=['disbursement_count']),
            models.Index(fields=['disbursement_total']),
        ]

    def __str__(self):
        return 'Recipient %s' % self.id

    def get_monitoring_users(self):
        details = self.bank_transfer_details.first()
        if details:
            return details.recipient_bank_account.monitoring_users
        return User.objects.none()


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


class PrisonerProfile(TimeStampedModel):
    credit_count = models.BigIntegerField(default=0)
    credit_total = models.BigIntegerField(default=0)
    disbursement_count = models.BigIntegerField(default=0)
    disbursement_total = models.BigIntegerField(default=0)

    prisoner_name = models.CharField(max_length=250)
    prisoner_number = models.CharField(max_length=250, db_index=True)
    single_offender_id = models.UUIDField(blank=True, null=True)
    prisoner_dob = models.DateField(blank=True, null=True)
    current_prison = models.ForeignKey(
        Prison, on_delete=models.SET_NULL, null=True, related_name='current_prisoners'
    )

    prisons = models.ManyToManyField(Prison, related_name='historic_prisoners')
    senders = models.ManyToManyField(SenderProfile, related_name='prisoners')
    recipients = models.ManyToManyField(RecipientProfile, related_name='prisoners')

    monitoring_users = models.ManyToManyField(
        User, related_name='monitored_prisoners'
    )

    objects = PrisonerProfileManager()

    class Meta:
        ordering = ('created',)
        permissions = (
            ('view_prisonerprofile', 'Can view prisoner profile'),
        )
        unique_together = (
            ('prisoner_number', 'prisoner_dob',),
        )
        indexes = [
            models.Index(fields=['credit_count']),
            models.Index(fields=['credit_total']),
            models.Index(fields=['disbursement_count']),
            models.Index(fields=['disbursement_total']),
        ]

    def __str__(self):
        return self.prisoner_number

    def get_monitoring_users(self):
        return self.monitoring_users


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
