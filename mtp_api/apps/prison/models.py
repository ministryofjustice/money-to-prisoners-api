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

    prison = models.ForeignKey(Prison)

    class Meta:
        index_together = [
            ["prisoner_number", "prisoner_dob"],
        ]
