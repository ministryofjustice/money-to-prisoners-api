import datetime
from io import StringIO
import pathlib

from django.urls import reverse
from django.utils import timezone
from model_mommy import mommy
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import ScheduledCommand
from core.tests.utils import create_super_admin, make_test_users
from core.utils import monday_of_same_week
from mtp_auth.tests.utils import AuthTestCaseMixin
from performance.models import PerformanceData


class PerformanceDataViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()

        test_users = make_test_users()
        self.send_money_user = test_users['send_money_users'][0]
        self.bank_admin_user = test_users['bank_admins'][0]
        self.prison_clerk_user = test_users['prison_clerks'][0]

    @property
    def performance_data_url(self):
        return reverse('performance-data')

    def test_only_accessible_from_send_money(self):
        for (user, expected_status_code) in [
            (self.send_money_user, status.HTTP_200_OK),
            (self.bank_admin_user, status.HTTP_403_FORBIDDEN),
            (self.prison_clerk_user, status.HTTP_403_FORBIDDEN),
        ]:
            http_auth_header = self.get_http_authorization_for_user(user)
            response = self.client.get(
                self.performance_data_url, data={}, format='json',
                HTTP_AUTHORIZATION=http_auth_header
            )
            self.assertEqual(response.status_code, expected_status_code,
                             f'expected {expected_status_code} for user {user}')

    def test_headers(self):
        response = self.client.get(
            self.performance_data_url, data={}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user),
        )

        self.assertDictEqual(
            response.json()['headers'],
            {
                'week': 'Week commencing',
                'credits_total': 'Transactions – total',
                'credits_by_mtp': 'Transactions – online',
                'digital_takeup': 'Digital take-up',
                'completion_rate': 'Completion rate',
                'user_satisfaction': 'User satisfaction',
                'rated_1': 'Very dissatisfied',
                'rated_2': 'Dissatisfied',
                'rated_3': 'Neither satisfied or dissatisfied',
                'rated_4': 'Satisfied',
                'rated_5': 'Very satisfied',
            }
        )

    def test_percentages_are_formatted(self):
        mommy.make(
            PerformanceData,
            week=self._monday_n_weeks_ago(4),
            digital_takeup=0.95,
            completion_rate=0.8111,
            user_satisfaction=0.96666666,
        )
        mommy.make(
            PerformanceData,
            week=self._monday_n_weeks_ago(3),
            digital_takeup=0.0,
            completion_rate=0.85,
            user_satisfaction=None,
        )

        response = self.client.get(
            self.performance_data_url, data={}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user),
        )

        older_week = response.json()['results'][0]
        self.assertEqual(older_week['digital_takeup'], '95%')
        self.assertEqual(older_week['completion_rate'], '81%')
        self.assertEqual(older_week['user_satisfaction'], '97%')

        # Testing difference between None and 0.0 (formatted as 0%)
        newer_week = response.json()['results'][1]
        self.assertEqual(newer_week['digital_takeup'], '0%')
        self.assertEqual(newer_week['completion_rate'], '85%')
        self.assertEqual(newer_week['user_satisfaction'], None)

    def test_filtering_by_week(self):
        records = []
        for age_weeks in [100, 50, 10]:
            records.append(
                mommy.make(PerformanceData, week=self._monday_n_weeks_ago(age_weeks))
            )

        # By default only last 52 weeks records are returned
        response = self.client.get(
            self.performance_data_url, data={}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['week'], str(records[1].week))  # 50 weeks old
        self.assertEqual(results[1]['week'], str(records[2].week))  # 10 weeks old

        # When filtering by week to limit results range
        params = {
            'week__gte': self._monday_n_weeks_ago(60),
            'week__lt': self._monday_n_weeks_ago(40),
        }
        response = self.client.get(
            self.performance_data_url, params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['week'], str(records[1].week))  # 50 weeks old

    def test_filtering_invalid_input(self):
        # One date valid, the other not valid
        params = {
            'week__gte': self._monday_n_weeks_ago(60),
            'week__lt': 'to boo 2031',
        }
        response = self.client.get(
            self.performance_data_url, params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Enter a valid date', response.json()['week__lt'])

        # Both "dates" not valid
        params = {
            'week__gte': '2021/10/01',
            'week__lt': 'to boo 2031',
        }
        response = self.client.get(
            self.performance_data_url, params, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn('Enter a valid date', body['week__gte'])
        self.assertIn('Enter a valid date', body['week__lt'])

    def _monday_n_weeks_ago(self, weeks_ago):
        """
        Returns the Monday of 'weeks_ago' weeks ago
        """

        monday = monday_of_same_week(timezone.localdate())
        return monday - datetime.timedelta(weeks=weeks_ago)


class UserSatisfactionUploadViewTestCase(AuthTestCaseMixin, APITestCase):

    def setUp(self):
        super().setUp()
        create_super_admin()

        self.upload_url = reverse('admin:user_satisfaction_upload')

    def test_triggers_update_performance_data(self):
        test_data = [
            # +------------+----------+------------------+
            # | start date | end date | expected week_to |
            # +------------+----------+------------------+
            ('2021-01-01', '2021-01-31', '2021-02-01'),  # last week is complete (Sunday)
            ('2021-07-01', '2021-07-31', '2021-07-31'),  # last week is incomplete
        ]
        for (start_date, end_date, expected_week_to) in test_data:
            test_csv = self.fake_csv(start_date, end_date)

            self.client.login(username='admin', password='adminadmin')
            self.client.post(
                self.upload_url,
                data={'csv_file': test_csv},
            )

            # Check 'update_performance_data' is scheduled correctly
            job = ScheduledCommand.objects.get(name='update_performance_data')
            self.assertEqual(job.arg_string, f'--week-from={start_date} --week-to={expected_week_to}')
            self.assertTrue(job.delete_after_next)
            self.assertEqual(job.cron_entry, '*/10 * * * *')
            job.delete()

    def fake_csv(self, start_date, end_date):
        test_csv = StringIO()
        test_csv.write('creation date,type,feedback\n')
        test_csv.write(f'{start_date} 00:00:00,aggregated-service-feedback,Rating of 5: 99\n')
        test_csv.write(f'{end_date} 00:00:00,aggregated-service-feedback,Rating of 5: 99\n')
        test_csv.seek(0)

        return test_csv


class DigitalTakeupUploadViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_nomis_mtp_prisons']

    def setUp(self):
        super().setUp()
        create_super_admin()

        self.upload_url = reverse('admin:digital_takeup_upload')
        self.fixture_path = pathlib.Path(__file__).parent / 'files'
        self.fixture_path = self.fixture_path / 'Money_to_Prisoner_Stats - 02.11.16.xls'

        self.test_week = datetime.date(2016, 10, 31)  # Monday of week containing 2nd Nov 2016

    def test_updates_performance_data_when_already_there(self):
        PerformanceData.objects.create(week=self.test_week)

        with self.fixture_path.open('rb') as f:
            self.client.login(username='admin', password='adminadmin')
            self.client.post(
                self.upload_url,
                data={'excel_file': f},
            )

        # Check 'update_performance_data' is scheduled correctly
        job = ScheduledCommand.objects.get(name='update_performance_data')
        week_to = self.test_week + datetime.timedelta(weeks=1)
        self.assertEqual(job.arg_string, f'--week-from={self.test_week} --week-to={week_to}')
        self.assertTrue(job.delete_after_next)
        self.assertEqual(job.cron_entry, '*/10 * * * *')

    def test_doesnt_update_performance_data_when_not_generated_yet(self):
        with self.fixture_path.open('rb') as f:
            self.client.login(username='admin', password='adminadmin')
            self.client.post(
                self.upload_url,
                data={'excel_file': f},
            )

        job = ScheduledCommand.objects.filter(name='update_performance_data')

        self.assertFalse(job.exists())
