import datetime
from types import MethodType
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model, user_logged_in
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from mtp_common.tasks import send_email

from core.models import TimeStampedModel
from prison.models import Prison


class PrisonUserMappingManager(models.Manager):
    def assign_prisons_from_user(self, from_user, to_user):
        prisons = self.get_prison_set_for_user(from_user)
        if len(prisons) > 0:
            self.assign_prisons_to_user(to_user, prisons)

    def assign_prisons_to_user(self, user, prisons):
        mapping, _ = self.get_or_create(user=user)
        if len(prisons):
            mapping.prisons.set(prisons)
        else:
            mapping.delete()

    def get_prison_set_for_user(self, user):
        try:
            return self.get_queryset().get(user=user).prisons.all()
        except PrisonUserMapping.DoesNotExist:
            return Prison.objects.none()


class PrisonUserMapping(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_comment='The user.')
    prisons = models.ManyToManyField('prison.Prison')
    objects = PrisonUserMappingManager()

    class Meta:
        db_table_comment = (
            'User accounts: links a staff user to the prisons they work with (see mtp_auth_prisonusermapping_prisons).'
        )

    def __str__(self):
        return self.user.username


class ApplicationUserMapping(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_comment='The user.')
    application = models.ForeignKey(
        'oauth2_provider.Application', on_delete=models.CASCADE,
        db_comment='An app the user may sign in to.',
    )

    class Meta:
        db_table_comment = 'User accounts: which Prisoner Money apps each user may sign in to.'

    def __str__(self):
        return '%s -> %s' % (self.user.username, self.application.client_id)


class RoleManager(models.Manager):
    def get_roles_for_user(self, user):
        return self.get_queryset().filter(key_group__in=user.groups.all())


class Role(models.Model):
    """
    This model defines the application and group mappings a user must have to fit into a specific role.
    Users must be in exactly one key group to be able to manage users. When a new user is created,
    they are assigned a role and gain access to associated application and groups. Separate logic also
    means that they inherit the creating/approving user's prison set (except from FIU)
    """
    name = models.CharField(
        max_length=30, unique=True, db_comment='Name of the role, such as prison-clerk or security.',
    )
    key_group = models.OneToOneField(
        'auth.Group', unique=True, on_delete=models.CASCADE,
        db_comment='The group that identifies users with this role. Users are given it when their account is created.',
    )
    other_groups = models.ManyToManyField('auth.Group', blank=True, related_name='+')
    application = models.ForeignKey(
        'oauth2_provider.Application', related_name='+', on_delete=models.CASCADE,
        db_comment='The app that users with this role sign in to.',
    )
    login_url = models.URLField(db_comment="Address of the app's sign-in page, used in emails to users.")

    objects = RoleManager()

    class Meta:
        db_table_comment = (
            'User accounts: the kinds of staff account, such as prison clerk or security staff, '
            'with the app and groups that each one is given.'
        )
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


class JobInformation(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_comment='The user.')
    title = models.CharField(max_length=255, db_comment='Job title, chosen from a list or typed in.')
    prison_estate = models.CharField(
        max_length=255, db_comment='Area of the prison estate the user works in: Local prison, Regional or National.',
    )
    tasks = models.TextField(db_comment="The user's description of their main tasks.")

    class Meta:
        db_table_comment = 'User accounts: job details that NOMS Ops users give the first time they sign in.'
        verbose_name_plural = 'job information'


class Login(models.Model):
    created = models.DateTimeField(auto_now_add=True, db_comment='When the user signed in.')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_comment='The user.')
    application = models.ForeignKey(
        'oauth2_provider.Application', on_delete=models.CASCADE, db_comment='The app signed in to.',
    )

    class Meta:
        db_table_comment = (
            'User accounts: each successful sign-in by a member of staff, used for the staff sign-ins report in '
            'the API admin site. Service accounts are not recorded. Deleted after a year.'
        )

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

        if failed_attempt_count >= settings.MTP_AUTH_LOCKOUT_COUNT:
            last_failed_attempt = failed_attempts.first()
            lockout_cutoff = now() - datetime.timedelta(
                seconds=settings.MTP_AUTH_LOCKOUT_LOCKOUT_PERIOD
            )
            if last_failed_attempt.created > lockout_cutoff:
                return True
            else:
                failed_attempts.delete()
        return False

    def is_lockout_imminent(self, user, client=None):
        failed_attempts = self.get_queryset().filter(user=user)
        if client:
            failed_attempts = failed_attempts.filter(application=client)
        failed_attempt_count = failed_attempts.count()
        return failed_attempt_count == (settings.MTP_AUTH_LOCKOUT_COUNT - 1)

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
                service_name = client.name.lower()
                login_url = roles[0].login_url
            else:
                service_name = 'prisoner money'
                login_url = ''
            send_email(
                template_name='api-account-locked',
                to=user.email,
                personalisation={
                    'service_name': service_name,
                    'name': user.get_full_name(),
                    'lockout_period': settings.MTP_AUTH_LOCKOUT_LOCKOUT_PERIOD // 60,
                    'login_url': login_url,
                },
                staff_email=True,
            )


class FailedLoginAttempt(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_comment='The user.')
    application = models.ForeignKey(
        'oauth2_provider.Application', on_delete=models.CASCADE, db_comment='The app the attempt was made on.',
    )

    objects = FailedLoginAttemptManager()

    class Meta:
        db_table_comment = (
            'User accounts: sign-in attempts with a wrong password. Too many in a row lock the account for a time. '
            'Cleared after a successful sign-in.'
        )
        ordering = ('-created',)

    def __str__(self):
        return self.user.username


class PasswordChangeRequest(TimeStampedModel):
    code = models.UUIDField(
        default=uuid.uuid4, primary_key=True, editable=False,
        db_comment='Code in the link emailed to the user.',
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_comment='The user.')

    class Meta:
        db_table_comment = (
            'User accounts: requests to reset a forgotten password, made through a link sent by email. '
            'Deleted after 12 hours.'
        )

    def __str__(self):
        return '{user} {created}'.format(user=self.user, created=self.created)


class AccountRequest(TimeStampedModel):
    # NB: these fields must be synchronised with any changes to the user model
    username = models.CharField(
        max_length=150, validators=[AbstractUser.username_validator], db_comment='Requested username.',
    )
    first_name = models.CharField(max_length=30, db_comment='First name.')
    last_name = models.CharField(max_length=30, db_comment='Last name.')
    email = models.EmailField(db_comment='Email address.')
    manager_email = models.EmailField(
        blank=True, null=True, db_comment="Line manager's email address; required for security staff.",
    )

    reason = models.TextField(blank=True, db_comment='Why the person needs an account.')
    role = models.ForeignKey(Role, related_name='+', on_delete=models.CASCADE, db_comment='The role requested.')
    prison = models.ForeignKey(
        Prison, related_name='+', on_delete=models.CASCADE, blank=True, null=True,
        db_comment='Prison the person works at; optional for security staff.',
    )

    class Meta:
        db_table_comment = (
            'User accounts: requests for a new staff account, made from the sign-in page of an app. '
            "Waiting for one of the app's user admins to accept or decline. Deleted once dealt with."
        )
        ordering = ('created',)

    def __str__(self):
        return 'Account request {model.username} > {model.role}, {model.prison}'.format(model=self)


class Flag(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='flags', db_comment='The user.',
    )
    name = models.SlugField(
        db_comment='Name of the flag, such as hmpps-employee, set by the apps to remember answers and messages seen.',
    )

    class Meta:
        db_table_comment = (
            'User accounts: named markers that the apps set on a user, such as that a message has been seen.'
        )
        unique_together = [('user', 'name')]

    def __str__(self):
        return self.name


def patch_user_model():
    user_model = get_user_model()

    # patch natural lookup of usernames to be case insensitive
    def get_by_natural_key(self, username):
        return self.get(**{'%s__iexact' % user_model.USERNAME_FIELD: username})

    user_model.objects.get_by_natural_key = MethodType(get_by_natural_key, user_model.objects)

    # add shortcut for checking non-app-specific lock-outs
    user_model.is_locked_out = property(lambda u: FailedLoginAttempt.objects.is_locked_out(user=u))

    # update default error messages
    username_field = user_model._meta.get_field('username')
    username_field.error_messages['unique'] = _('That username already exists')
