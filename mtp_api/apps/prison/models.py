from django.db import models

from model_utils.models import TimeStampedModel


class Prison(TimeStampedModel):
    name = models.CharField(max_length=500)

    def __unicode__(self):
        return self.name
