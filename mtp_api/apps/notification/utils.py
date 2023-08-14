from datetime import datetime, timedelta, time

from django.utils import timezone

from notification.constants import EmailFrequency


def get_notification_period(email_frequency: EmailFrequency):
    """
    Returns start and end datetime of previous day, week, or month
    NB: only DAILY is currently supported in noms-ops and email-sending management command
    """
    today = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    if email_frequency == EmailFrequency.daily:
        return today - timedelta(days=1), today
    elif email_frequency == EmailFrequency.weekly:
        start_of_this_week = today - timedelta(days=today.weekday())
        return start_of_this_week - timedelta(days=7), start_of_this_week
    elif email_frequency == EmailFrequency.monthly:
        first = today.replace(day=1)
        return (first - timedelta(days=1)).replace(day=1), first
    elif email_frequency == EmailFrequency.never:
        return today, today - timedelta(days=1)
    raise ValueError
