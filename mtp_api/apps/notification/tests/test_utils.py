import datetime
import unittest
from unittest import mock

import pytz

from notification.constants import EMAIL_FREQUENCY, get_notification_period


class TimePeriodTestCase(unittest.TestCase):
    @mock.patch('notification.constants.timezone.now')
    def test_daily(self, now):
        tz = pytz.timezone('Europe/London')
        now.return_value = datetime.datetime(2019, 7, 17, 12).astimezone(tz)
        self.assertEqual(
            get_notification_period(EMAIL_FREQUENCY.DAILY),
            (datetime.datetime(2019, 7, 16).astimezone(tz), datetime.datetime(2019, 7, 17).astimezone(tz))
        )

    @mock.patch('notification.constants.timezone.now')
    def test_weekly(self, now):
        tz = pytz.timezone('Europe/London')
        now.return_value = datetime.datetime(2019, 7, 17, 12).astimezone(tz)
        self.assertEqual(
            get_notification_period(EMAIL_FREQUENCY.WEEKLY),
            (datetime.datetime(2019, 7, 8).astimezone(tz), datetime.datetime(2019, 7, 15).astimezone(tz))
        )

    @mock.patch('notification.constants.timezone.now')
    def test_monthly(self, now):
        tz = pytz.timezone('Europe/London')
        now.return_value = datetime.datetime(2019, 7, 17, 12).astimezone(tz)
        self.assertEqual(
            get_notification_period(EMAIL_FREQUENCY.MONTHLY),
            (datetime.datetime(2019, 6, 1).astimezone(tz), datetime.datetime(2019, 7, 1).astimezone(tz))
        )

    @mock.patch('notification.constants.timezone.now')
    def test_never(self, now):
        tz = pytz.timezone('Europe/London')
        now.return_value = datetime.datetime(2019, 7, 17, 12).astimezone(tz)
        period_start, period_end = get_notification_period(EMAIL_FREQUENCY.NEVER)
        self.assertGreater(period_start, period_end, 'Time period should be an empty range')

    @mock.patch('notification.constants.timezone.now')
    def test_invalid(self, now):
        tz = pytz.timezone('Europe/London')
        now.return_value = datetime.datetime(2019, 7, 17, 12).astimezone(tz)
        with self.assertRaises(KeyError):
            get_notification_period('yesterday')
