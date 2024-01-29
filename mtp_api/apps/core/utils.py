import datetime

from django.core.management import CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date


def monday_of_same_week(date: datetime.date) -> datetime.date:
    """
    Returns the Monday of the same week as date

    How it works: datetime.date.weekday() returns 0 for Monday, 1 for Tuesday
    and so on. So effectively it's the number of days you need to go back in
    order to return to Monday.
    """

    monday = date - datetime.timedelta(days=date.weekday())
    return monday

def date_argument(argument) -> datetime.datetime:
    if not argument:
        return None
    date = parse_date(argument)
    if not date:
        raise CommandError('Cannot parse date')
    return beginning_of_day(date)

def beginning_of_day(date) -> datetime.datetime:
    return timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))
