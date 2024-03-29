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
    service = models.CharField(max_length=50, choices=Service.choices)
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)
    message_to_users = models.CharField(max_length=255, blank=True)

    objects = DowntimeManager()

    class Meta:
        ordering = ('-end', '-start')

    def __str__(self):
        return '%s, %s -> %s' % (self.service, self.start, self.end)


class Notification(models.Model):
    public = models.BooleanField(default=False, help_text='Notifications must be public to be seen before login')
    target = models.CharField(max_length=30, choices=NotificationTarget.choices)
    level = models.SmallIntegerField(choices=sorted(
        (level, capfirst(name))
        for level, name in messages.DEFAULT_TAGS.items()
        if level > 10
    ))
    start = models.DateTimeField(default=timezone.now)
    end = models.DateTimeField(null=True, blank=True)
    headline = models.CharField(max_length=200)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ('-end', '-start')

    def __str__(self):
        return self.headline

    @property
    def level_label(self):
        return messages.DEFAULT_TAGS.get(self.level, messages.DEFAULT_TAGS[messages.ERROR])
