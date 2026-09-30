import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from core.models import ScheduledCommand, TimeStampedModel
from prison.models import Prison
from security.constants import CheckStatus
from security.managers import (
    PrisonerProfileManager, SenderProfileManager, RecipientProfileManager,
    MonitoredPartialEmailAddressManager,
    CheckManager, CheckAutoAcceptRuleManager,
)
from security.signals import prisoner_profile_current_prisons_need_updating

logger = logging.getLogger('mtp')


class SenderProfile(TimeStampedModel):
    credit_count = models.BigIntegerField(default=0, db_comment='Number of credits from this sender.')
    credit_total = models.BigIntegerField(default=0, db_comment='Total of credits from this sender, in pence.')

    prisons = models.ManyToManyField(Prison, related_name='senders')

    objects = SenderProfileManager()

    class Meta:
        db_table_comment = (
            'Security: one row for each person or account that has sent money, grouping their credits. '
            'Their details are in security_banktransfersenderdetails or security_debitcardsenderdetails.'
        )
        ordering = ('created',)
        indexes = [
            models.Index(fields=['credit_count']),
            models.Index(fields=['credit_total']),
        ]

    def __str__(self):
        return f'Sender {self.id}'

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
    sort_code = models.CharField(max_length=50, blank=True, db_comment='Sort code.')
    account_number = models.CharField(max_length=50, blank=True, db_comment='Account number.')
    roll_number = models.CharField(
        max_length=50, blank=True, db_comment='Building society roll number, if the account has one.',
    )

    monitoring_users = models.ManyToManyField(
        User, related_name='monitored_bank_accounts'
    )

    class Meta:
        db_table_comment = (
            'Security: bank accounts that bank transfers have come from or disbursements have been paid to.'
        )
        unique_together = (
            ('sort_code', 'account_number', 'roll_number'),
        )

    def __str__(self):
        return (
            'BankAccount{sort_code=%s, account_number=%s, roll_number=%s}' %
            (self.sort_code, self.account_number, self.roll_number or 'n/a')
        )


class BankTransferSenderDetails(TimeStampedModel):
    sender_name = models.CharField(max_length=250, blank=True, db_comment="Sender's name from the bank statement.")
    sender_bank_account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='senders', db_comment="The sender's bank account.",
    )
    sender = models.ForeignKey(
        SenderProfile, on_delete=models.CASCADE, related_name='bank_transfer_details',
        db_comment='The sender profile these details belong to.',
    )

    class Meta:
        db_table_comment = 'Security: the name and bank account of a sender who has sent money by bank transfer.'
        ordering = ('created',)
        verbose_name_plural = 'bank transfer sender details'

    def __str__(self):
        return self.sender_name


class DebitCardSenderDetails(TimeStampedModel):
    card_number_last_digits = models.CharField(
        max_length=4, blank=True, null=True, db_index=True, db_comment='Last 4 digits of the card number.',
    )
    card_expiry_date = models.CharField(
        max_length=5, blank=True, null=True, db_comment='Card expiry date, as MM/YY.',
    )
    postcode = models.CharField(
        max_length=250, blank=True, null=True, db_index=True, db_comment="Postcode of the card's billing address.",
    )
    sender = models.ForeignKey(
        SenderProfile, on_delete=models.CASCADE, related_name='debit_card_details',
        db_comment='The sender profile these details belong to.',
    )

    monitoring_users = models.ManyToManyField(
        User, related_name='monitored_debit_cards'
    )

    class Meta:
        db_table_comment = (
            'Security: a debit card that money has been sent with, identified by the last 4 digits of its number, '
            'its expiry date and its billing postcode. The full card number is never stored.'
        )
        ordering = ('created',)
        verbose_name_plural = 'debit card sender details'
        unique_together = (
            ('card_number_last_digits', 'card_expiry_date', 'postcode',),
        )

    def __str__(self):
        return '%s %s' % (self.card_number_last_digits, self.card_expiry_date)


class CardholderName(models.Model):
    name = models.CharField(max_length=250, db_comment='Name on the card, as given in GOV.UK Pay.')
    debit_card_sender_details = models.ForeignKey(
        DebitCardSenderDetails, on_delete=models.CASCADE,
        related_name='cardholder_names', related_query_name='cardholder_name',
        db_comment='The debit card.',
    )

    class Meta:
        db_table_comment = 'Security: each different cardholder name used with a debit card.'
        ordering = ('pk',)

    def __str__(self):
        return self.name


class SenderEmail(models.Model):
    email = models.CharField(max_length=250, db_comment='Email address given by the sender on Send Money.')
    debit_card_sender_details = models.ForeignKey(
        DebitCardSenderDetails, on_delete=models.CASCADE,
        related_name='sender_emails', related_query_name='sender_email',
        db_comment='The debit card.',
    )

    class Meta:
        db_table_comment = 'Security: each different email address given by senders paying with a debit card.'
        ordering = ('pk',)

    def __str__(self):
        return self.email


class RecipientProfile(TimeStampedModel):
    disbursement_count = models.BigIntegerField(default=0, db_comment='Number of disbursements to this recipient.')
    disbursement_total = models.BigIntegerField(
        default=0, db_comment='Total of disbursements to this recipient, in pence.',
    )

    prisons = models.ManyToManyField(Prison, related_name='recipients')

    objects = RecipientProfileManager()

    class Meta:
        db_table_comment = (
            'Security: one row for each person or company that prisoners have sent money to, grouping their '
            'disbursements. Bank account details are in security_banktransferrecipientdetails.'
        )
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
        BankAccount, on_delete=models.CASCADE, related_name='recipients', db_comment="The recipient's bank account.",
    )
    recipient = models.ForeignKey(
        RecipientProfile, on_delete=models.CASCADE, related_name='bank_transfer_details',
        db_comment='The recipient profile these details belong to.',
    )

    class Meta:
        db_table_comment = 'Security: the bank account of a recipient who has been paid by bank transfer.'
        ordering = ('created',)
        verbose_name_plural = 'bank transfer recipient details'


class PrisonerProfile(TimeStampedModel):
    credit_count = models.BigIntegerField(default=0, db_comment='Number of credits to this prisoner.')
    credit_total = models.BigIntegerField(default=0, db_comment='Total of credits to this prisoner, in pence.')
    disbursement_count = models.BigIntegerField(default=0, db_comment='Number of disbursements from this prisoner.')
    disbursement_total = models.BigIntegerField(
        default=0, db_comment='Total of disbursements from this prisoner, in pence.',
    )

    prisoner_name = models.CharField(max_length=250, db_comment="Prisoner's name, from NOMIS.")
    prisoner_number = models.CharField(max_length=250, db_index=True, db_comment='Prisoner number.')
    prisoner_dob = models.DateField(blank=True, null=True, db_comment="Prisoner's date of birth.")
    current_prison = models.ForeignKey(
        Prison, on_delete=models.SET_NULL, null=True, related_name='current_prisoners',
        db_comment='Prison the prisoner is in now, from prison_prisonerlocation; empty if they have no current '
                   'location, such as after release.',
    )

    prisons = models.ManyToManyField(Prison, related_name='historic_prisoners')
    senders = models.ManyToManyField(SenderProfile, related_name='prisoners')
    recipients = models.ManyToManyField(RecipientProfile, related_name='prisoners')

    monitoring_users = models.ManyToManyField(
        User, related_name='monitored_prisoners'
    )

    objects = PrisonerProfileManager()

    class Meta:
        db_table_comment = (
            'Security: one row for each prisoner who has received or sent money, grouping their credits and '
            'disbursements.'
        )
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
        return f'Prisoner {self.id} ({self.prisoner_number})'

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
    name = models.CharField(max_length=250, db_comment='Name for the prisoner as typed by a sender.')
    prisoner = models.ForeignKey(
        PrisonerProfile, on_delete=models.CASCADE,
        related_name='provided_names', related_query_name='provided_name',
        db_comment='The prisoner profile.',
    )

    class Meta:
        db_table_comment = 'Security: each different name that senders have typed for a prisoner on Send Money.'
        ordering = ('pk',)

    def __str__(self):
        return self.name


class SavedSearch(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_comment='The NOMS Ops user who saved the search.')
    description = models.CharField(max_length=255, db_comment='Name of the search shown to the user.')
    endpoint = models.CharField(max_length=255, db_comment='The API address the search is run against.')
    last_result_count = models.IntegerField(
        default=0, db_comment='Number of results when the user last looked, so that new results can be counted.',
    )
    site_url = models.CharField(
        max_length=1000, null=True, blank=True, db_comment='Address of the page in NOMS Ops that shows the search.',
    )

    class Meta:
        db_table_comment = (
            'Security: searches and pages that NOMS Ops users have chosen to follow, with the search values '
            'in security_searchfilter.'
        )
        ordering = ('created',)

    def __str__(self):
        return '{user}: {title}'.format(user=self.user.username, title=self.description)


class SearchFilter(models.Model):
    field = models.CharField(max_length=255, db_comment='Name of the search field.')
    value = models.CharField(max_length=255, db_comment='Value searched for.')
    saved_search = models.ForeignKey(
        SavedSearch, on_delete=models.CASCADE, related_name='filters', db_comment='The saved search.',
    )

    class Meta:
        db_table_comment = 'Security: the search values of each saved search.'

    def __str__(self):
        return '{field}={value}'.format(field=self.field, value=self.value)


class MonitoredPartialEmailAddress(TimeStampedModel):
    keyword = models.CharField(
        max_length=255, unique=True, validators=[MinLengthValidator(3)], error_messages={
            'unique': _('Keyword already exists.'),
        },
        db_comment='Part of an email address, in lower case and at least 3 characters long.',
    )

    objects = MonitoredPartialEmailAddressManager()

    class Meta:
        db_table_comment = 'Security: parts of email addresses entered by security staff in NOMS Ops.'
        ordering = ('keyword',)
        verbose_name = 'monitored partial email address'
        verbose_name_plural = 'monitored partial email addresses'

    def __str__(self):
        return self.keyword

    def matches(self, email_address: str) -> bool:
        return self.keyword in email_address.lower()


class Check(TimeStampedModel):
    credit = models.OneToOneField(
        'credit.Credit',
        on_delete=models.CASCADE,
        related_name='security_check',
        db_comment='The credit being checked.',
    )
    status = models.CharField(
        max_length=50,
        choices=CheckStatus.choices,
        db_index=True,
        db_comment='pending: waiting for a decision; accepted: the credit may go ahead; '
                   'rejected: the credit is to be refunded.',
    )
    description = ArrayField(
        models.CharField(max_length=200),
        null=True,
        blank=True,
        db_comment='Text shown to security staff saying why the credit needs checking.',
    )
    rules = ArrayField(
        models.CharField(max_length=50),
        null=True,
        blank=True,
        db_comment='Codes of the rules that led to the check.',
    )
    actioned_at = models.DateTimeField(null=True, blank=True, db_comment='When the check was accepted or rejected.')
    actioned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_check_actioned_by',
        db_comment='Who accepted or rejected the check.',
    )
    decision_reason = models.TextField(blank=True, db_comment='Note given by the person who made the decision.')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_check_assigned_to',
        db_comment='The member of security staff dealing with the check.',
    )
    rejection_reasons = models.JSONField(
        name='rejection_reasons',
        default=dict,
        db_comment='The reasons chosen when the check was rejected.',
    )
    # We persist AutoAcceptRuleState for three reasons:
    # 1. To link an applicable AutoAcceptRule to the Check, even if not active
    #   * This is for the use case where someone wants to re-activate an deactivated auto-accept rule
    # 2. To determine whether the rule was active by value of CheckAutoAcceptRuleState.active
    #   * In the historic views we render those whose acceptance was mediated by an active auto-accept rule
    #      differently from those that simply had a deactivated auto accept rule and were accepted manually
    # 3. What the reason was at the time of auto-acceptance
    #   * In the historic views, for the auto accept rules, we render the auto-accept rule reason active at the time,
    #      not the most recent
    auto_accept_rule_state = models.ForeignKey(
        'security.CheckAutoAcceptRuleState',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checks',
        db_comment='The auto-accept rule, as it stood at the time, that applied to this credit, if any.',
    )

    objects = CheckManager()

    class Meta:
        db_table_comment = (
            'Security: credits that security staff need to accept or reject before prison staff can credit them. '
            'At most one per credit.'
        )

    def accept(self, by, reason=''):
        """
        Accepts a check.

        :raise: django.core.exceptions.ValidationError if the check is in status 'rejected'.
        """
        if self.status == CheckStatus.accepted.value:
            return

        if self.status == CheckStatus.rejected.value:
            raise ValidationError({
                'status': ValidationError(_('Cannot accept a rejected check.'), 'conflict'),
            })

        self.status = CheckStatus.accepted.value
        self.actioned_by = by
        self.actioned_at = now()
        self.decision_reason = reason
        self.save()

    def reject(self, by, reason, rejection_reasons):
        """
        Rejects a check.

        :raise: django.core.exceptions.ValidationError if the check is in status 'accepted'.
        """
        if self.status == CheckStatus.rejected.value:
            return

        if self.status == CheckStatus.accepted.value:
            raise ValidationError({
                'status': ValidationError(_('Cannot reject an accepted check.'), 'conflict'),
            })

        self.status = CheckStatus.rejected.value
        self.actioned_by = by
        self.actioned_at = now()
        self.decision_reason = reason
        self.rejection_reasons = rejection_reasons
        self.save()

    def __str__(self):
        return f'Check {self.status} for {self.credit}'


class CheckAutoAcceptRule(TimeStampedModel):
    debit_card_sender_details = models.ForeignKey(
        DebitCardSenderDetails, on_delete=models.CASCADE, related_name='check_auto_accept_rules',
        db_comment='The debit card.',
    )
    prisoner_profile = models.ForeignKey(
        PrisonerProfile, on_delete=models.CASCADE, related_name='check_auto_accept_rules',
        db_comment='The prisoner.',
    )

    objects = CheckAutoAcceptRuleManager()

    def get_latest_state(self):
        return self.states.order_by('-created').first()

    def is_active(self):
        return self.get_latest_state().active

    class Meta:
        db_table_comment = (
            'Security: pairs of debit card and prisoner whose credits security staff have agreed to accept '
            'without checking each time. Whether each is switched on is in security_checkautoacceptrulestate.'
        )
        ordering = ('created',)
        unique_together = (
            ('debit_card_sender_details', 'prisoner_profile',),
        )


class CheckAutoAcceptRuleState(TimeStampedModel):
    auto_accept_rule = models.ForeignKey(
        CheckAutoAcceptRule, on_delete=models.CASCADE, related_name='states', db_comment='The auto-accept rule.',
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_check_auto_accept_rule_state_added_by',
        db_comment='Who switched the rule on or off.',
    )
    active = models.BooleanField(db_comment='Whether the rule was switched on.')
    reason = models.TextField(db_comment='Reason given for the change.')

    class Meta:
        db_table_comment = (
            'Security: history of each auto-accept rule being switched on or off. The latest row is the current state.'
        )
        ordering = ('created',)


@receiver(prisoner_profile_current_prisons_need_updating)
def update_current_prisons(**kwargs):
    job = ScheduledCommand(
        name='update_current_prisons',
        arg_string='',
        cron_entry='*/10 * * * *',
        delete_after_next=True
    )
    job.save()
