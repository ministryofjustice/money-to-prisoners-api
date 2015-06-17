from django.db import models

from model_utils.models import TimeStampedModel


class Prison(TimeStampedModel):
    nomis_id = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=500)

    def __unicode__(self):
        return self.name
