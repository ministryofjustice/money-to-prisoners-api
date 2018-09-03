from datetime import date, timedelta

from django.utils.translation import gettext_lazy as _
from extended_choices import Choices


TIME_PERIOD = Choices(
    ('ALL_TIME', 'all_time', _('All time')),
    ('LAST_7_DAYS', 'last_7_days', _('Last 7 days')),
    ('LAST_30_DAYS', 'last_30_days', _('Last 30 days')),
    ('LAST_6_MONTHS', 'last_6_months', _('Last 6 months')),
)


def get_start_date_for_time_period(time_period):
    if time_period == TIME_PERIOD.LAST_7_DAYS:
        return date.today() - timedelta(days=7)
    elif time_period == TIME_PERIOD.LAST_30_DAYS:
        return date.today() - timedelta(days=30)
    elif time_period == TIME_PERIOD.LAST_6_MONTHS:
        return date.today() - timedelta(days=180)
    else:
        return date(1970, 1, 1)
