from datetime import datetime, timedelta, time

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from extended_choices import Choices


EMAIL_FREQUENCY = Choices(
    ('NEVER', 'never', _('Never')),
    ('DAILY', 'daily', _('Daily')),
    ('WEEKLY', 'weekly', _('Weekly')),
    ('MONTHLY', 'monthly', _('Monthly')),
)


def get_notification_period_start(email_frequency):
    today = timezone.make_aware(
        datetime.combine(timezone.now(), time.min)
    )
    if email_frequency == EMAIL_FREQUENCY.DAILY:
        return today - timedelta(days=1)
    elif email_frequency == EMAIL_FREQUENCY.WEEKLY:
        return today - timedelta(days=7)
    elif email_frequency == EMAIL_FREQUENCY.MONTHLY:
        # returns first day of previous month
        first = today.replace(day=1)
        return (first - timedelta(days=1)).replace(day=1)
