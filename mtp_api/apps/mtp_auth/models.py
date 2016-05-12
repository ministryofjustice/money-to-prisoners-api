import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from prison.models import Prison


class PrisonUserMappingManager(models.Manager):

    def get_prison_set_for_user(self, user):
        try:
            return PrisonUserMapping.objects.get(user=user).prisons.all()
        except PrisonUserMapping.DoesNotExist:
            return Prison.objects.none()


class PrisonUserMapping(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    prisons = models.ManyToManyField('prison.Prison')
    objects = PrisonUserMappingManager()

    def __str__(self):
        return self.user.username


class ApplicationUserMapping(TimeStampedModel):

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    application = models.ForeignKey('oauth2_provider.Application', on_delete=models.CASCADE)

    def __str__(self):
        return '%s -> %s' % (self.user.username, self.application.client_id)


class ApplicationGroupMapping(TimeStampedModel):

    group = models.ForeignKey('auth.Group', on_delete=models.CASCADE)
    application = models.ForeignKey('oauth2_provider.Application', on_delete=models.CASCADE)

    def __str__(self):
        return '%s -> %s' % (self.group.name, self.application.client_id)


class FailedLoginAttemptManager(models.Manager):
    def is_locked_out(self, user, client=None):
        failed_attempts = self.get_queryset().filter(user=user)
        if client:
            failed_attempts = failed_attempts.filter(application=client)
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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    application = models.ForeignKey('oauth2_provider.Application', on_delete=models.CASCADE)

    objects = FailedLoginAttemptManager()

    class Meta:
        ordering = ('-created',)

    def __str__(self):
        return self.user.username


def patch_user_model():
    user_model = get_user_model()

    # add shortcut for chechking non-app-specific lock-outs
    user_model.is_locked_out = property(lambda u: FailedLoginAttempt.objects.is_locked_out(user=u))

    # update default error messages
    username_field = user_model._meta.get_field('username')
    username_field.error_messages['unique'] = _('That username already exists')
