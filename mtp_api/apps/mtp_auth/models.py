import datetime

from django.conf import settings
from django.db import models
from django.utils.timezone import now
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


class FailedLoginAttemptManager(models.Manager):
    def is_locked_out(self, user, client):
        failed_attempts = self.get_queryset().filter(
            user=user,
            application=client,
        )
        failed_attempt_count = failed_attempts.count()
        if not failed_attempt_count:
            return False

        last_failed_attempt = failed_attempts.first()
        lockout_period = datetime.timedelta(seconds=settings.MTP_AUTH_LOCKOUT_LOCKOUT_PERIOD)
        return failed_attempt_count >= settings.MTP_AUTH_LOCKOUT_COUNT and \
            last_failed_attempt.created > now() - lockout_period

    def delete_failed_attempts(self, user, client):
        self.get_queryset().filter(
            user=user,
            application=client,
        ).delete()

    def add_failed_attempt(self, user, client):
        self.get_queryset().create(
            user=user,
            application=client,
        )


class FailedLoginAttempt(TimeStampedModel):
    user = models.ForeignKey('auth.User')
    application = models.ForeignKey('oauth2_provider.Application')

    objects = FailedLoginAttemptManager()

    class Meta:
        ordering = ('-created',)

    def __str__(self):
        return self.user.username
