import re

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from model_utils.models import TimeStampedModel

validate_prisoner_number = RegexValidator(r'^[A-Z]\d{4}[A-Z]{2}$', message=_('Invalid prisoner number'))


class Population(models.Model):
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=255)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.description


class Category(models.Model):
    name = models.CharField(max_length=30)
    description = models.CharField(max_length=255)

    class Meta:
        ordering = ('name',)
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.description


class Prison(TimeStampedModel):
    nomis_id = models.CharField(max_length=3, primary_key=True, verbose_name='NOMIS id')
    general_ledger_code = models.CharField(max_length=8)
    name = models.CharField(max_length=500)
    region = models.CharField(max_length=255, blank=True)
    populations = models.ManyToManyField(Population)
    categories = models.ManyToManyField(Category)
    pre_approval_required = models.BooleanField(default=False)

    private_estate = models.BooleanField(default=False)
    use_nomis_for_balances = models.BooleanField(default=True)
    cms_establishment_code = models.CharField(max_length=10, blank=True)

    name_prefixes = ('HMP/YOI', 'HMP', 'HMYOI/RC', 'HMYOI', 'IRC', 'STC')
    re_prefixes = re.compile(r'^(%s)?' % (' |'.join(('HMP & YOI', 'HMYOI & RC') + name_prefixes) + ' '))

    class Meta:
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
    prison = models.OneToOneField(Prison, on_delete=models.CASCADE)

    address_line1 = models.CharField(max_length=250)
    address_line2 = models.CharField(max_length=250, blank=True)
    city = models.CharField(max_length=250)
    postcode = models.CharField(max_length=250)

    sort_code = models.CharField(max_length=50)
    account_number = models.CharField(max_length=50)

    class Meta:
        ordering = ('prison',)

    def __str__(self):
        return self.prison.name

    @property
    def address(self):
        return ', '.join(
            filter(None, (self.address_line1, self.address_line2, self.city, self.postcode))
        )


class RemittanceEmail(models.Model):
    prison = models.ForeignKey(Prison, on_delete=models.CASCADE)
    email = models.EmailField()

    class Meta:
        ordering = ('prison',)

    def __str__(self):
        return self.prison.name


class PrisonerLocation(TimeStampedModel):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.SET_NULL)

    prisoner_name = models.CharField(blank=True, max_length=250)
    prisoner_number = models.CharField(max_length=250)
    prisoner_dob = models.DateField()
    prison = models.ForeignKey(Prison, on_delete=models.CASCADE)
    active = models.BooleanField(default=False, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['prisoner_number', 'prisoner_dob']),
        ]
        ordering = ('prisoner_number',)
        get_latest_by = 'created'

    def __str__(self):
        return '%s (%s)' % (self.prisoner_name, self.prisoner_number)


class PrisonerCreditNoticeEmail(models.Model):
    prison = models.OneToOneField(Prison, on_delete=models.CASCADE)
    email = models.EmailField()

    class Meta:
        ordering = ('prison',)

    def __str__(self):
        return f'{self.prison.name} <{self.email}>'


class PrisonerBalance(TimeStampedModel):
    prisoner_number = models.CharField(max_length=250, primary_key=True)
    prison = models.ForeignKey(Prison, on_delete=models.CASCADE)
    amount = models.BigIntegerField()

    class Meta:
        indexes = [
            models.Index(fields=['prisoner_number', 'prison']),
        ]

    def __str__(self):
        return f'{self.prisoner_number} has balance £{self.amount/100:0.2f}'
