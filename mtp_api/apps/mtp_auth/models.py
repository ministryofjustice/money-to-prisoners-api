from django.db import models

from model_utils.models import TimeStampedModel


class PrisonUserMapping(TimeStampedModel):

    user = models.OneToOneField('auth.User')
    prisons = models.ManyToManyField('prison.Prison')

    def __str__(self):
        return self.user.username
