from django.conf import settings
from django.db import models

from model_utils.models import TimeStampedModel


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
    general_ledger_code = models.CharField(max_length=3)
    name = models.CharField(max_length=500)
    region = models.CharField(max_length=255, blank=True)
    populations = models.ManyToManyField(Population)
    categories = models.ManyToManyField(Category)
    pre_approval_required = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class PrisonerLocation(TimeStampedModel):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    prisoner_name = models.CharField(blank=True, max_length=250)
    prisoner_number = models.CharField(max_length=250)  # TODO: shouldn't this be unique?
    prisoner_dob = models.DateField()

    prison = models.ForeignKey(Prison, on_delete=models.CASCADE)

    class Meta:
        index_together = (
            ('prisoner_number', 'prisoner_dob'),
        )

    def __str__(self):
        return '%s (%s)' % (self.prisoner_name, self.prisoner_number)
