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


def get_notification_period(email_frequency):
    """
    Returns start and end datetime of previous day, week, or month
    """
    today = timezone.make_aware(
        datetime.combine(timezone.now(), time.min)
    )
    if email_frequency == EMAIL_FREQUENCY.DAILY:
        return today - timedelta(days=1), today
    elif email_frequency == EMAIL_FREQUENCY.WEEKLY:
        start_of_this_week = today - timedelta(days=today.weekday())
        return start_of_this_week - timedelta(days=7), start_of_this_week
    elif email_frequency == EMAIL_FREQUENCY.MONTHLY:
        first = today.replace(day=1)
        return (first - timedelta(days=1)).replace(day=1), first
