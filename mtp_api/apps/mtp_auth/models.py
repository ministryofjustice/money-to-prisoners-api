from django.db import models

from model_utils.models import TimeStampedModel


class PrisonUserMapping(TimeStampedModel):

    user = models.OneToOneField('auth.User')
    prisons = models.ManyToManyField('prison.Prison')

    def __str__(self):
        return self.user.username


class ApplicationUserMapping(TimeStampedModel):

    user = models.ForeignKey('auth.User')
    application = models.ForeignKey('oauth2_provider.Application')

    def __str__(self):
        return self.user.username
