from django.contrib import messages
from django.db import models
from django.utils import timezone
from django.utils.text import capfirst

from service.constants import NotificationTarget, Service


class DowntimeManager(models.Manager):
    def active_downtime(self, service: Service):
        now = timezone.now()
        return self.filter(
            models.Q(start__lte=now, end__gt=now) |
            models.Q(start__lte=now, end=None),
            service=service,
        ).order_by('-end').first()


class Downtime(models.Model):
    service = models.CharField(
        max_length=50, choices=Service.choices,
        db_comment='The outside service that is unavailable. Currently only gov_uk_pay.',
    )
    start = models.DateTimeField(db_comment='When the service stops being available.')
    end = models.DateTimeField(null=True, blank=True, db_comment='When it is back; empty if not yet known.')
    message_to_users = models.CharField(max_length=255, blank=True, db_comment='Message to show to users.')

    objects = DowntimeManager()

    class Meta:
        db_table_comment = (
            'Service: times when an outside service, such as GOV.UK Pay, is unavailable, '
            'so that Send Money can warn senders.'
        )
        ordering = ('-end', '-start')

    def __str__(self):
        return '%s, %s -> %s' % (self.service, self.start, self.end)


class Notification(models.Model):
    public = models.BooleanField(
        default=False, help_text='Notifications must be public to be seen before login',
        db_comment='Whether the message can be seen before signing in.',
    )
    target = models.CharField(
        max_length=30, choices=NotificationTarget.choices,
        db_comment='Where the message appears, such as the Cashbook dashboard.',
    )
    level = models.SmallIntegerField(
        choices=sorted(
            (level, capfirst(name))
            for level, name in messages.DEFAULT_TAGS.items()
            if level > 10
        ),
        db_comment='How the message is shown: 20 information, 25 success, 30 warning, 40 error.',
    )
    start = models.DateTimeField(default=timezone.now, db_comment='When to start showing the message.')
    end = models.DateTimeField(
        null=True, blank=True,
        db_comment='When to stop showing it; empty to show it until removed.',
    )
    headline = models.CharField(max_length=200, db_comment='Headline of the message.')
    message = models.TextField(blank=True, db_comment='Body of the message.')

    class Meta:
        db_table_comment = 'Service: messages shown to users of the Prisoner Money apps, such as planned maintenance.'
        ordering = ('-end', '-start')

    def __str__(self):
        return self.headline

    @property
    def level_label(self):
        return messages.DEFAULT_TAGS.get(self.level, messages.DEFAULT_TAGS[messages.ERROR])
