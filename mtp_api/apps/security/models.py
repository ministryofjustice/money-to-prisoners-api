import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField, JSONField
from django.core.exceptions import ValidationError
from django.db import models
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from core.models import ScheduledCommand
from prison.models import Prison
from security.constants import CHECK_STATUS
from security.managers import (
    PrisonerProfileManager, SenderProfileManager, RecipientProfileManager,
    CheckManager,
)
from security.signals import prisoner_profile_current_prisons_need_updating

logger = logging.getLogger('mtp')


class SenderProfile(TimeStampedModel):
    credit_count = models.BigIntegerField(default=0)
    credit_total = models.BigIntegerField(default=0)

    prisons = models.ManyToManyField(Prison, related_name='senders')

    objects = SenderProfileManager()

    class Meta:
        ordering = ('created',)
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

    def add_prison(self, prison):
        logger.info('Associating Sender Profile: %s with Prison %s', self, prison)
        self.prisons.add(prison)

    def remove_prison(self, prison):
        logger.info('Removing association between Sender Profile %s and Prison %s', self, prison)
        self.prisons.remove(prison)


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

    def add_sender(self, sender_profile):
        logger.info('Associating Prisoner Profile: %s with Sender Profile %s', self, sender_profile)
        self.senders.add(sender_profile)

    def remove_sender(self, sender_profile):
        logger.info('Removing association between Prisoner Profile %s and Sender Profile %s', self, sender_profile)
        self.senders.remove(sender_profile)

    def add_prison(self, prison):
        logger.info('Associating Prisoner Profile: %s with Prison %s', self, prison)
        self.prisons.add(prison)


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


class Check(TimeStampedModel):
    credit = models.OneToOneField(
        'credit.Credit',
        on_delete=models.CASCADE,
        related_name='security_check',
    )
    status = models.CharField(
        max_length=50,
        choices=CHECK_STATUS,
        db_index=True,
    )
    description = ArrayField(
        models.CharField(max_length=200),
        null=True,
        blank=True,
    )
    rules = ArrayField(
        models.CharField(max_length=50),
        null=True,
        blank=True,
    )
    actioned_at = models.DateTimeField(null=True, blank=True)
    actioned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_check_actioned_by'
    )
    decision_reason = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_check_assigned_to'
    )
    rejection_reasons = JSONField(
        name='rejection_reasons',
        default=dict
    )

    objects = CheckManager()

    def accept(self, by, reason=''):
        """
        Accepts a check.

        :raise: django.core.exceptions.ValidationError if the check is in status 'rejected'.
        """
        if self.status == CHECK_STATUS.ACCEPTED:
            return

        if self.status == CHECK_STATUS.REJECTED:
            raise ValidationError({
                'status': ValidationError(_('Cannot accept a rejected check.'), 'conflict'),
            })

        self.status = CHECK_STATUS.ACCEPTED
        self.actioned_by = by
        self.actioned_at = now()
        self.decision_reason = reason
        self.save()

    def reject(self, by, reason, rejection_reasons):
        """
        Rejects a check.

        :raise: django.core.exceptions.ValidationError if the check is in status 'accepted'.
        """
        if self.status == CHECK_STATUS.REJECTED:
            return

        if self.status == CHECK_STATUS.ACCEPTED:
            raise ValidationError({
                'status': ValidationError(_('Cannot reject an accepted check.'), 'conflict'),
            })

        self.status = CHECK_STATUS.REJECTED
        self.actioned_by = by
        self.actioned_at = now()
        self.decision_reason = reason
        self.rejection_reasons = rejection_reasons
        self.save()

    def __str__(self):
        return f'Check {self.status} for {self.credit}'


@receiver(prisoner_profile_current_prisons_need_updating)
def update_current_prisons(**kwargs):
    job = ScheduledCommand(
        name='update_current_prisons',
        arg_string='',
        cron_entry='*/10 * * * *',
        delete_after_next=True
    )
    job.save()
