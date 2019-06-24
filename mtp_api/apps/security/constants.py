from datetime import timedelta, time, datetime

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from extended_choices import Choices


TIME_PERIOD = Choices(
    ('ALL_TIME', 'all_time', _('all time')),
    ('LAST_7_DAYS', 'last_7_days', _('last 7 days')),
    ('LAST_4_WEEKS', 'last_4_weeks', _('last 4 weeks')),
    ('LAST_6_MONTHS', 'last_6_months', _('last 6 months')),
)


def get_start_date_for_time_period(time_period):
    today = timezone.make_aware(
        datetime.combine(timezone.now(), time.min)
    )
    if time_period == TIME_PERIOD.LAST_7_DAYS:
        return today - timedelta(days=7)
    elif time_period == TIME_PERIOD.LAST_4_WEEKS:
        return today - timedelta(days=28)
    elif time_period == TIME_PERIOD.LAST_6_MONTHS:
        return today - timedelta(days=180)
    else:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
