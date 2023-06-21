import datetime
import unittest
from unittest import mock

from django.utils import timezone

from notification.constants import EmailFrequency
from notification.utils import get_notification_period


def make_local_datetime(year, month, day, hour=0):
    return timezone.make_aware(datetime.datetime(year, month, day, hour))


class TimePeriodTestCase(unittest.TestCase):
    @mock.patch('notification.utils.timezone.now')
    def test_daily(self, now):
        now.return_value = make_local_datetime(2019, 7, 17, 12)
        self.assertEqual(
            get_notification_period(EmailFrequency.daily),
            (make_local_datetime(2019, 7, 16), make_local_datetime(2019, 7, 17))
        )

    @mock.patch('notification.utils.timezone.now')
    def test_weekly(self, now):
        now.return_value = make_local_datetime(2019, 7, 17, 12)
        self.assertEqual(
            get_notification_period(EmailFrequency.weekly),
            (make_local_datetime(2019, 7, 8), make_local_datetime(2019, 7, 15))
        )

    @mock.patch('notification.utils.timezone.now')
    def test_monthly(self, now):
        now.return_value = make_local_datetime(2019, 7, 17, 12)
        self.assertEqual(
            get_notification_period(EmailFrequency.monthly),
            (make_local_datetime(2019, 6, 1), make_local_datetime(2019, 7, 1))
        )

    @mock.patch('notification.utils.timezone.now')
    def test_never(self, now):
        now.return_value = make_local_datetime(2019, 7, 17, 12)
        period_start, period_end = get_notification_period(EmailFrequency.never)
        self.assertGreater(period_start, period_end, 'Time period should be an empty range')

    @mock.patch('notification.utils.timezone.now')
    def test_invalid(self, now):
        now.return_value = make_local_datetime(2019, 7, 17, 12)
        with self.assertRaises(ValueError):
            get_notification_period('yesterday')
