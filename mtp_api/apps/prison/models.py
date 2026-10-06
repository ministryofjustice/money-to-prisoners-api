import datetime
import re

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.crypto import salted_hmac
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel

validate_prisoner_number = RegexValidator(r'^[A-Z]\d{4}[A-Z]{2}$', message=_('Invalid prisoner number'))


class Population(models.Model):
    name = models.CharField(max_length=30, db_comment='Short code, such as young.')
    description = models.CharField(max_length=255, db_comment='Name shown to users, such as Young offender.')

    class Meta:
        db_table_comment = 'Prisons: kinds of people a prison holds, such as male, female, adult or young offender.'
        ordering = ('name',)

    def __str__(self):
        return self.description


class Category(models.Model):
    name = models.CharField(max_length=30, db_comment='Short code, such as B or IRC.')
    description = models.CharField(max_length=255, db_comment='Name shown to users, such as Category B.')

    class Meta:
        db_table_comment = (
            'Prisons: kinds of prison, such as category A to D, young offender institution '
            'or immigration removal centre.'
        )
        ordering = ('name',)
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.description


class Prison(TimeStampedModel):
    nomis_id = models.CharField(
        max_length=3, primary_key=True, verbose_name='NOMIS id',
        db_comment='Code for the prison in NOMIS, such as BXI.',
    )
    general_ledger_code = models.CharField(
        max_length=8,
        db_comment="The prison's business unit code in the finance system, used in the journals Bank Admin produces.",
    )
    name = models.CharField(max_length=500, db_comment='Full name of the prison.')
    region = models.CharField(max_length=255, blank=True, db_comment='Region the prison is in.')
    populations = models.ManyToManyField(Population)
    categories = models.ManyToManyField(Category)
    pre_approval_required = models.BooleanField(
        default=False,
        db_comment='Whether security staff review credits for this prison before prison staff credit them.',
    )

    private_estate = models.BooleanField(
        default=False,
        db_comment='Whether the prison is privately run. Bank Admin sends its credits to it each day.',
    )
    use_nomis_for_balances = models.BooleanField(
        default=True,
        db_comment="Whether prisoners' account balances come from NOMIS. "
                   'If not, they come from prison_prisonerbalance.',
    )
    cms_establishment_code = models.CharField(
        max_length=10, blank=True,
        db_comment='Code used in the name of the daily credits file sent to a privately run prison.',
    )

    name_prefixes = ('HMP/YOI', 'HMP', 'HMYOI/RC', 'HMYOI', 'IRC', 'STC')
    re_prefixes = re.compile(r'^(%s)?' % (' |'.join(('HMP & YOI', 'HMYOI & RC') + name_prefixes) + ' '))

    class Meta:
        db_table_comment = 'Prisons: prisons and other establishments that prisoners can be sent money in.'
        ordering = ('name',)

    @classmethod
    def shorten_name(cls, name):
        return cls.re_prefixes.sub('', name.upper()).title()

    def __str__(self):
        return self.name

    @property
    def short_name(self):
        return self.shorten_name(self.name)


class PrisonBankAccount(models.Model):
    prison = models.OneToOneField(Prison, on_delete=models.CASCADE, db_comment='The privately run prison.')

    address_line1 = models.CharField(max_length=250, db_comment='First line of the postal address.')
    address_line2 = models.CharField(max_length=250, blank=True, db_comment='Second line of the postal address.')
    city = models.CharField(max_length=250, db_comment='Town or city.')
    postcode = models.CharField(max_length=250, db_comment='Postcode.')

    sort_code = models.CharField(max_length=50, db_comment='Sort code of the bank account.')
    account_number = models.CharField(max_length=50, db_comment='Account number of the bank account.')

    class Meta:
        db_table_comment = (
            "Prisons: bank account and address of a privately run prison, which the prison's daily credits are "
            'paid into.'
        )
        ordering = ('prison',)

    def __str__(self):
        return self.prison.name

    @property
    def address(self):
        return ', '.join(
            filter(None, (self.address_line1, self.address_line2, self.city, self.postcode))
        )


class RemittanceEmail(models.Model):
    prison = models.ForeignKey(Prison, on_delete=models.CASCADE, db_comment='The privately run prison.')
    email = models.EmailField(db_comment='Email address.')

    class Meta:
        db_table_comment = "Prisons: email addresses that a privately run prison's daily credits file is sent to."
        ordering = ('prison',)

    def __str__(self):
        return self.prison.name


class PrisonerLocation(TimeStampedModel):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.SET_NULL,
        db_comment='Who uploaded the record.',
    )

    prisoner_name = models.CharField(blank=True, max_length=250, db_comment="Prisoner's name, from NOMIS.")
    prisoner_number = models.CharField(max_length=250, db_comment='Prisoner number, from NOMIS.')
    prisoner_dob = models.DateField(db_comment="Prisoner's date of birth, from NOMIS.")
    prison = models.ForeignKey(Prison, on_delete=models.CASCADE, db_comment='Prison the prisoner is in.')
    active = models.BooleanField(
        default=False, db_index=True,
        db_comment='Whether this is a current record. Records stay inactive until their whole upload has finished.',
    )

    class Meta:
        db_table_comment = (
            'Prisons: which prison each prisoner is in, uploaded from NOMIS through NOMS Ops. '
            'Used to check the details senders give and to match credits to prisoners.'
        )
        indexes = [
            models.Index(fields=['prisoner_number', 'prisoner_dob']),
        ]
        ordering = ('prisoner_number',)
        get_latest_by = 'created'

    def __str__(self):
        return '%s (%s)' % (self.prisoner_name, self.prisoner_number)


class PrisonerCreditNoticeEmail(models.Model):
    prison = models.OneToOneField(Prison, on_delete=models.CASCADE, db_comment='The prison.')
    email = models.EmailField(db_comment='Email address.')

    class Meta:
        db_table_comment = (
            'Prisons: the email address that each prison is sent its daily credit notices at, '
            'for printing and handing to prisoners.'
        )
        ordering = ('prison',)

    def __str__(self):
        return f'{self.prison.name} <{self.email}>'


class PrisonerBalance(TimeStampedModel):
    prisoner_number = models.CharField(max_length=250, primary_key=True, db_comment='Prisoner number.')
    prison = models.ForeignKey(Prison, on_delete=models.CASCADE, db_comment='Prison the prisoner is in.')
    amount = models.BigIntegerField(db_comment='Balance, in pence.')

    class Meta:
        db_table_comment = (
            "Prisons: prisoners' account balances at prisons that do not use NOMIS for them, uploaded through "
            'the API admin site. Only balances above a set amount are uploaded, so a missing row means a low balance.'
        )
        indexes = [
            models.Index(fields=['prisoner_number', 'prison']),
        ]

    def __str__(self):
        return f'{self.prisoner_number} has balance £{self.amount/100:0.2f}'


class PrisonerValidityAttemptManager(models.Manager):
    def hash_prisoner_number(self, prisoner_number):
        return salted_hmac('prisoner_validity', prisoner_number.strip().upper(), algorithm='sha256').hexdigest()

    def hash_prisoner_details(self, prisoner_number, prisoner_dob):
        """
        Hashes the number and date of birth together so that repeated guessing of a date of birth can be told
        apart from the same details being submitted repeatedly, without storing the date of birth itself.
        """
        details = '%s|%s' % (prisoner_number.strip().upper(), prisoner_dob.isoformat() if prisoner_dob else '')
        return salted_hmac('prisoner_validity_details', details, algorithm='sha256').hexdigest()

    def in_window(self, ip_address):
        window_start = now() - datetime.timedelta(seconds=settings.PRISONER_VALIDITY_WINDOW_SECONDS)
        return self.get_queryset().filter(ip_address=ip_address, created__gte=window_start)

    def is_rate_limited(self, ip_address):
        """
        Returns (limited, retry_after_seconds) for an IP address.
        Only failed checks in the window count. An address is limited when its failed checks reach the failure limit,
        cover too many distinct prisoners, or try too many distinct prisoner number and date of birth combinations.
        Matched checks never count, so organisations and shared connections that look up many prisoners correctly
        are not limited.
        An unknown IP address is never limited.
        """
        if not settings.PRISONER_VALIDITY_LIMITING_ENABLED or not ip_address:
            return False, 0
        failed_attempts = self.in_window(ip_address).filter(matched=False)

        def last_seen(field):
            # when each distinct value was last tried; rows recorded before the details hash existed have none
            return (
                failed_attempts.exclude(**{field: ''}).order_by().values(field)
                .annotate(last_seen=models.Max('created')).values_list('last_seen', flat=True)
            )

        unblocked_from = [
            self.limit_expires_from(failed_attempts.values_list('created', flat=True),
                                    settings.PRISONER_VALIDITY_FAILURE_LIMIT),
            self.limit_expires_from(last_seen('prisoner_number_hash'),
                                    settings.PRISONER_VALIDITY_DISTINCT_PRISONER_LIMIT),
            self.limit_expires_from(last_seen('prisoner_details_hash'),
                                    settings.PRISONER_VALIDITY_DISTINCT_DETAILS_LIMIT),
        ]
        unblocked_from = [when for when in unblocked_from if when]
        if not unblocked_from:
            return False, 0
        # every limit that applies must have expired
        window = datetime.timedelta(seconds=settings.PRISONER_VALIDITY_WINDOW_SECONDS)
        retry_after = int((max(unblocked_from) + window - now()).total_seconds())
        return True, max(retry_after, 1)

    @staticmethod
    def limit_expires_from(last_seen_times, limit):
        """
        Given when each counted thing was last seen in the window, returns the time whose expiry brings the count
        back under the limit, or None if the count is already under it
        """
        last_seen_times = sorted(last_seen_times)
        excess = len(last_seen_times) - limit
        if excess < 0:
            return None
        return last_seen_times[excess]

    def record(self, ip_address, prisoner_number, prisoner_dob, matched):
        return self.get_queryset().create(
            ip_address=ip_address or None,
            prisoner_number_hash=self.hash_prisoner_number(prisoner_number),
            prisoner_details_hash=self.hash_prisoner_details(prisoner_number, prisoner_dob),
            matched=matched,
        )

    def delete_older_than(self, days):
        return self.get_queryset().filter(created__lt=now() - datetime.timedelta(days=days)).delete()


class PrisonerValidityAttempt(TimeStampedModel):
    """
    A record of each prisoner validity check made from the public send-money service.
    The prisoner number and date of birth are stored only as keyed hashes, never in readable form.
    Counting distinct prisoner_number_hash values for an address shows how many prisoners were looked up;
    counting distinct prisoner_details_hash values shows whether the date of birth was being guessed.
    """
    ip_address = models.GenericIPAddressField(
        blank=True, null=True, db_index=True,
        db_comment='IP address the check came from.',
    )
    prisoner_number_hash = models.CharField(
        max_length=64, db_index=True,
        db_comment='Keyed hash of the prisoner number. The number itself is not stored.',
    )
    prisoner_details_hash = models.CharField(
        max_length=64, db_index=True, blank=True,
        db_comment='Keyed hash of the prisoner number and date of birth together.',
    )
    matched = models.BooleanField(db_comment='Whether the details matched a prisoner.')

    objects = PrisonerValidityAttemptManager()

    class Meta:
        db_table_comment = (
            'Prisons: each check made on Send Money that a prisoner number and date of birth match a prisoner, '
            'used to limit repeated guessing. Old records are deleted.'
        )
        indexes = [
            models.Index(fields=['ip_address', 'created']),
        ]
        ordering = ('-created',)
        get_latest_by = 'created'

    def __str__(self):
        outcome = 'matched' if self.matched else 'not found'
        return f'{self.ip_address or "unknown IP"} {outcome} at {self.created:%Y-%m-%d %H:%M}'
