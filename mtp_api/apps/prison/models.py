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


class PrisonerLocation(TimeStampedModel):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.SET_NULL)

    prisoner_name = models.CharField(blank=True, max_length=250)
    prisoner_number = models.CharField(max_length=250)  # TODO: shouldn't this be unique?
    single_offender_id = models.UUIDField(blank=True, null=True)
    prisoner_dob = models.DateField()
    prison = models.ForeignKey(Prison, on_delete=models.CASCADE)
    active = models.BooleanField(default=False)

    class Meta:
        permissions = (
            ('view_prisonerlocation', 'Can view prisoner location'),
        )
        index_together = (
            ('prisoner_number', 'prisoner_dob'),
        )
        ordering = ('prisoner_number',)
        get_latest_by = 'created'

    def __str__(self):
        return '%s (%s)' % (self.prisoner_name, self.prisoner_number)


class PrisonerCreditNoticeEmail(models.Model):
    prison = models.OneToOneField(Prison)
    email = models.EmailField()

    class Meta:
        ordering = ('prison',)

    def __str__(self):
        return '%s <%s>' % (self.prison.name, self.email)
