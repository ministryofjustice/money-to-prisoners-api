import hashlib

from django.conf import settings
from django.db import models

from model_utils.models import TimeStampedModel


class Prison(TimeStampedModel):
    nomis_id = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=500)

    def __str__(self):
        return self.name


class PrisonerLocation(TimeStampedModel):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL)

    prisoner_number = models.CharField(max_length=250)
    prisoner_dob = models.DateField()

    # SHA256 of prisoner_number + prisoner_dob to that it can
    # be used for db joins
    prisoner_hash = models.CharField(max_length=250)

    prison = models.ForeignKey(Prison)

    def _calculate_prisoner_hash(self):
        original = '{number}_{dob}'.format(
            number=self.prisoner_number.lower(),
            dob=self.prisoner_dob.strftime('%m/%d/%Y')
        )
        hash_object = hashlib.sha256(original.encode())
        return hash_object.hexdigest()

    def save(self, *args, **kwargs):
        self.prisoner_hash = self._calculate_prisoner_hash()
        return super(PrisonerLocation, self).save(*args, **kwargs)
