from django.db import models
from django.utils import timezone
from extended_choices import Choices

SERVICES = Choices(
    ('GOV_UK_PAY', 'gov_uk_pay', 'GOV.UK Pay'),
)


class DowntimeManager(models.Manager):

    def active_downtime(self, service):
        now = timezone.now()
        return self.filter(
            models.Q(start__lte=now, end__gt=now) |
            models.Q(start__lte=now, end=None),
            service=service
        ).order_by('-end').first()


class Downtime(models.Model):
    service = models.CharField(max_length=50, choices=SERVICES)
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)

    objects = DowntimeManager()

    def __str__(self):
        return '%s, %s -> %s' % (self.service, self.start, self.end)
