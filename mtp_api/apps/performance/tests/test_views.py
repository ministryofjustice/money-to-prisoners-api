import datetime

from django.urls import reverse
from django.utils import timezone
from model_mommy import mommy
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
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

        response = self.client.get(
            self.performance_data_url, data={}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user),
        )

        first_result = response.json()['results'][0]
        self.assertEqual(first_result['digital_takeup'], '95%')
        self.assertEqual(first_result['completion_rate'], '81%')
        self.assertEqual(first_result['user_satisfaction'], '97%')

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
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['week'], str(records[1].week))  # 50 weeks old

    def _monday_n_weeks_ago(self, weeks_ago):
        """
        Returns the Monday of 'weeks_ago' weeks ago
        """

        year, week, _ = timezone.localdate().isocalendar()
        monday = datetime.date.fromisocalendar(year, week, 1)  # 1 = Monday
        return monday - datetime.timedelta(weeks=weeks_ago)
