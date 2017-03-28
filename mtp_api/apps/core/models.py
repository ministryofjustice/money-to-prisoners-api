import logging
from datetime import timedelta
from time import perf_counter as pc

from crontab import CronTab
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command, get_commands
from django.db import models
from django.db.models.functions.datetime import TruncBase
from django.dispatch import receiver
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger('mtp')


def validate_command_name(value):
    if value not in get_commands():
        raise ValidationError(_('"%s" is not a recognised command') % value)


def validate_cron_entry(value):
    try:
        CronTab(value)
    except ValueError as e:
        raise ValidationError(_('"%(entry)s" is not a valid cron entry: %(error)s') % {
            'entry': value, 'error': e
        })


class ScheduledCommand(models.Model):
    name = models.CharField(max_length=255, validators=[validate_command_name])
    arg_string = models.CharField(max_length=255, blank=True)
    cron_entry = models.CharField(max_length=255, validators=[validate_cron_entry])
    next_execution = models.DateTimeField(null=True, blank=True)
    delete_after_next = models.BooleanField(default=False)

    def get_args(self):
        return self.arg_string.split(' ') if self.arg_string else []

    def run(self):
        logger.info('Running scheduled command "%s"' % (self))
        self.update_next_execution()
        self.save()
        start = pc()
        call_command(self.name, *self.get_args())
        logger.info('Completed scheduled command "%s" in %ss' % (self, pc() - start))
        if self.delete_after_next:
            self.delete()

    def is_scheduled(self):
        return timezone.now() >= self.next_execution

    def update_next_execution(self):
        self.next_execution = timezone.now() + timedelta(seconds=CronTab(self.cron_entry).next())

    def __str__(self):
        return '%s %s' % (self.name, self.arg_string)


@receiver(models.signals.pre_save, sender=ScheduledCommand)
def set_next_execution(sender, instance, **kwargs):
    if instance.next_execution is None:
        instance.update_next_execution()


class TruncUtcDate(TruncBase):
    lookup_name = 'utcdate'

    @cached_property
    def output_field(self):
        return models.DateField()

    def as_sql(self, compiler, connection):
        lhs, lhs_params = compiler.compile(self.lhs)
        tzname = 'utc' if settings.USE_TZ else None
        sql, tz_params = connection.ops.datetime_cast_date_sql(lhs, tzname)
        lhs_params.extend(tz_params)
        return sql, lhs_params


models.DateTimeField.register_lookup(TruncUtcDate)
