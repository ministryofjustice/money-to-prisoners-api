from datetime import timedelta
import json

from django.test import TestCase
from django.utils import timezone

from service.models import Downtime, SERVICES


class DowntimeTestCase(TestCase):
    def _downtime_is_active(self, service, start, end):
        downtime = Downtime(service=service, start=start, end=end)
        downtime.save()

        active_downtime = Downtime.objects.active_downtime(service)
        self.assertIsNotNone(active_downtime)
        return active_downtime

    def _downtime_is_not_active(self, service, start, end):
        downtime = Downtime(service=service, start=start, end=end)
        downtime.save()

        active_downtime = Downtime.objects.active_downtime(service)
        self.assertIsNone(active_downtime)

    def test_downtime_with_start_is_active_after_start(self):
        one_hour_ago = timezone.now() - timedelta(hours=1)
        self._downtime_is_active(SERVICES.GOV_UK_PAY, one_hour_ago, None)

    def test_downtime_with_both_times_is_active_within_time_period(self):
        one_hour_ago = timezone.now() - timedelta(hours=1)
        in_one_hour = timezone.now() + timedelta(hours=1)
        self._downtime_is_active(SERVICES.GOV_UK_PAY, one_hour_ago, in_one_hour)

    def test_downtime_with_only_start_is_not_active_before_start(self):
        in_one_hour = timezone.now() + timedelta(hours=1)
        self._downtime_is_not_active(SERVICES.GOV_UK_PAY, in_one_hour, None)

    def test_downtime_withboth_times_is_not_active_before_start(self):
        in_one_hour = timezone.now() + timedelta(hours=1)
        in_two_hours = timezone.now() + timedelta(hours=2)
        self._downtime_is_not_active(SERVICES.GOV_UK_PAY, in_one_hour, in_two_hours)

    def test_downtime_with_both_times_is_not_active_after_end(self):
        two_hours_ago = timezone.now() - timedelta(hours=2)
        one_hour_ago = timezone.now() - timedelta(hours=1)
        self._downtime_is_not_active(SERVICES.GOV_UK_PAY, two_hours_ago, one_hour_ago)

    def test_multiple_downtimes_shows_latest_active_end(self):
        one_hour_ago = timezone.now() - timedelta(hours=1)
        in_one_hour = timezone.now() + timedelta(hours=1)
        earlier_downtime = Downtime(
            service=SERVICES.GOV_UK_PAY, start=one_hour_ago, end=in_one_hour)
        earlier_downtime.save()

        in_two_hours = timezone.now() + timedelta(hours=2)
        later_downtime = Downtime(
            service=SERVICES.GOV_UK_PAY, start=one_hour_ago, end=in_two_hours)
        later_downtime.save()

        in_three_hours = timezone.now() + timedelta(hours=3)
        later_inactive_downtime = Downtime(
            service=SERVICES.GOV_UK_PAY, start=in_one_hour, end=in_three_hours)
        later_inactive_downtime.save()

        active_downtime = Downtime.objects.active_downtime(SERVICES.GOV_UK_PAY)
        self.assertEqual(active_downtime.end, later_downtime.end)


class DowntimeHealthcheckTestCase(TestCase):
    def _get_healthcheck_data(self):
        response = self.client.get('/service-availability/')
        return json.loads(str(response.content, 'utf-8'))

    def test_healthcheck_returns_active_downtime(self):
        one_hour_ago = timezone.now() - timedelta(hours=1)
        in_one_hour = timezone.now() + timedelta(hours=1)
        downtime = Downtime(service=SERVICES.GOV_UK_PAY, start=one_hour_ago, end=in_one_hour)
        downtime.save()

        data = self._get_healthcheck_data()
        self.assertFalse(data['*']['status'])
        self.assertFalse(data['gov_uk_pay']['status'])
        self.assertEqual(data['gov_uk_pay']['downtime_end'], in_one_hour.isoformat())
        self.assertNotIn('message_to_users', data['gov_uk_pay'])

    def test_healthcheck_returns_active_downtime_with_no_end(self):
        one_hour_ago = timezone.now() - timedelta(hours=1)
        downtime = Downtime(service=SERVICES.GOV_UK_PAY, start=one_hour_ago, end=None)
        downtime.save()

        data = self._get_healthcheck_data()
        self.assertFalse(data['*']['status'])
        self.assertFalse(data['gov_uk_pay']['status'])
        self.assertNotIn('downtime_end', data['gov_uk_pay'])
        self.assertNotIn('message_to_users', data['gov_uk_pay'])

    def test_healthcheck_returns_active_downtime_with_message_to_users(self):
        one_hour_ago = timezone.now() - timedelta(hours=1)
        downtime = Downtime(service=SERVICES.GOV_UK_PAY, start=one_hour_ago, end=None)
        downtime.message_to_users = 'We’re making some changes to the site'
        downtime.save()

        data = self._get_healthcheck_data()
        self.assertFalse(data['*']['status'])
        self.assertFalse(data['gov_uk_pay']['status'])
        self.assertEqual(data['gov_uk_pay']['message_to_users'], 'We’re making some changes to the site')

    def test_healthcheck_returns_no_downtime(self):
        data = self._get_healthcheck_data()
        self.assertTrue(data['*']['status'])
        self.assertTrue(data['gov_uk_pay']['status'])
