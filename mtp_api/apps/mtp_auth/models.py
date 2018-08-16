import datetime
from types import MethodType
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model, user_logged_in
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext, gettext_lazy as _
from model_utils.models import TimeStampedModel
from mtp_common.tasks import send_email

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


class RoleManager(models.Manager):
    def get_roles_for_user(self, user):
        return self.get_queryset().filter(key_group__in=user.groups.all())

    def get_managed_roles_for_user(self, user):
        for role in self.get_roles_for_user(user):
            yield role
            yield from role.managed_roles.all()


class Role(models.Model):
    """
    This model defines the application and group mappings a user must have to fit into a specific role.
    Users must be in exactly one key group to be able to manage users. When a new user is created,
    they are assigned a role and gain access to associated application and groups. Separate logic also
    means that they inherit the creating user's prison set.
    """
    name = models.CharField(max_length=30, unique=True)
    key_group = models.OneToOneField('auth.Group', unique=True, on_delete=models.CASCADE)
    other_groups = models.ManyToManyField('auth.Group', blank=True, related_name='+')
    application = models.ForeignKey('oauth2_provider.Application', related_name='+', on_delete=models.CASCADE)
    managed_roles = models.ManyToManyField('self', blank=True)
    login_url = models.URLField(null=True)

    objects = RoleManager()

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name

    @property
    def groups(self):
        return [self.key_group] + list(self.other_groups.all())

    def assign_to_user(self, user):
        ApplicationUserMapping.objects.get_or_create(user=user, application=self.application)
        for group in self.groups:
            user.groups.add(group)


class Login(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    application = models.ForeignKey('oauth2_provider.Application', on_delete=models.CASCADE)

    ignored_usernames = {
        'transaction-uploader', 'prisoner-location-uploader',
        'send-money', 'bank-admin-cacher', '_token_retrieval',
    }

    @classmethod
    def user_logged_in(cls, sender, request, user, **kwargs):
        application = getattr(request, 'client', None)
        if not application:
            return
        if user.username in cls.ignored_usernames:
            return
        cls.objects.create(user=user, application=application)

    def __str__(self):
        return '%s logged into %s' % (self.user.username, self.application.name)


user_logged_in.connect(Login.user_logged_in)


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
        failed_attempts = self.get_queryset().filter(user=user, application=client)
        if failed_attempts.count() == settings.MTP_AUTH_LOCKOUT_COUNT:
            roles = Role.objects.get_roles_for_user(user)
            roles = list(filter(lambda role: role.application == client, roles))
            if roles:
                service_name = client.name
                login_url = roles[0].login_url
            else:
                service_name = None
                login_url = None
            email_context = {
                'service_name': service_name,
                'lockout_period': settings.MTP_AUTH_LOCKOUT_LOCKOUT_PERIOD // 60,
                'login_url': login_url,
            }
            send_email(
                user.email, 'mtp_auth/account_locked.txt',
                gettext('Your %(service_name)s account is temporarily locked') % email_context,
                context=email_context, html_template='mtp_auth/account_locked.html',
                anymail_tags=['account-locked'],
            )


class FailedLoginAttempt(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    application = models.ForeignKey('oauth2_provider.Application', on_delete=models.CASCADE)

    objects = FailedLoginAttemptManager()

    class Meta:
        ordering = ('-created',)

    def __str__(self):
        return self.user.username


class PasswordChangeRequest(TimeStampedModel):
    code = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return '{user} {created}'.format(user=self.user, created=self.created)


def patch_user_model():
    user_model = get_user_model()

    # patch natural lookup of usernames to be case insensitive
    def get_by_natural_key(self, username):
        return self.get(**{'%s__iexact' % user_model.USERNAME_FIELD: username})

    user_model.objects.get_by_natural_key = MethodType(get_by_natural_key, user_model.objects)

    # add shortcut for chechking non-app-specific lock-outs
    user_model.is_locked_out = property(lambda u: FailedLoginAttempt.objects.is_locked_out(user=u))

    # update default error messages
    username_field = user_model._meta.get_field('username')
    username_field.error_messages['unique'] = _('That username already exists')
