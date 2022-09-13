import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.dateformat import format as date_format
from django.utils.timezone import make_aware
from model_bakery import baker
from oauth2_provider.models import Application

from mtp_auth.models import Login, PrisonUserMapping
from mtp_auth.views import LoginStatsView
from prison.models import Prison

User = get_user_model()


class LoginCountTestCase(TestCase):
    def login(self, user, application, date):
        now = make_aware(datetime.datetime(*date, 12))
        with mock.patch('django.db.models.fields.timezone.now', return_value=now):
            Login.objects.create(
                user=user,
                application=application,
            )

    def test_login_counts(self):
        application = Application.objects.create(
            client_id='test-app',
            client_secret='test-app',
            client_type='confidential',
            authorization_grant_type='password',
            name='Test App',
            user=baker.make(User),
        )
        prison = baker.make(Prison, nomis_id='ABC')
        user_in_prison = baker.make(User)
        another_user_in_prison = baker.make(User)
        baker.make(PrisonUserMapping, user=user_in_prison, prisons=[prison])
        baker.make(PrisonUserMapping, user=another_user_in_prison, prisons=[prison])
        user_not_in_prison = baker.make(User)

        # last month: 3 login in prison
        self.login(user_in_prison, application, (2018, 3, 10))
        self.login(another_user_in_prison, application, (2018, 3, 17))
        self.login(user_in_prison, application, (2018, 3, 28))
        # this month: 2 logins in prison, 1 not linked to a prison
        self.login(user_in_prison, application, (2018, 4, 10))
        self.login(another_user_in_prison, application, (2018, 4, 11))
        self.login(user_not_in_prison, application, (2018, 4, 10))

        now = make_aware(datetime.datetime(2018, 4, 15, 12))
        with mock.patch('mtp_auth.views.timezone.localtime', return_value=now):
            view = LoginStatsView()
            current_month_progress, months = view.current_month_progress, view.months

        # "today" midday is roughly half way through April
        self.assertAlmostEqual(current_month_progress, 0.5, delta=0.02)

        this_month, last_month, *_ = months
        this_month = date_format(this_month, 'Y-m')
        last_month = date_format(last_month, 'Y-m')

        login_counts = view.get_login_counts(application.client_id)

        # expect there to be double by the end of the month
        self.assertEqual(login_counts[(prison.nomis_id, this_month)], 4)
        self.assertEqual(login_counts[(None, this_month)], 2)
        self.assertEqual(login_counts[(prison.nomis_id, last_month)], 3)
        self.assertEqual(login_counts[(None, last_month)], 0)

    def test_get_months(self):
        scenarios = [
            {
                'name': 'no edge cases',
                'now': make_aware(datetime.datetime(2020, 11, 15, 12)),
                'expected_months': [
                    make_aware(datetime.datetime(2020, 11, 1)),
                    make_aware(datetime.datetime(2020, 10, 1)),
                    make_aware(datetime.datetime(2020, 9, 1)),
                    make_aware(datetime.datetime(2020, 8, 1)),
                ],
            },
            {
                'name': 'crossing DST',
                'now': make_aware(datetime.datetime(2020, 5, 15, 12)),
                'expected_months': [
                    make_aware(datetime.datetime(2020, 5, 1)),
                    make_aware(datetime.datetime(2020, 4, 1)),
                    make_aware(datetime.datetime(2020, 3, 1)),
                    make_aware(datetime.datetime(2020, 2, 1)),
                ],
            },
            {
                'name': 'crossing year',
                'now': make_aware(datetime.datetime(2021, 1, 10, 12)),
                'expected_months': [
                    make_aware(datetime.datetime(2021, 1, 1)),
                    make_aware(datetime.datetime(2020, 12, 1)),
                    make_aware(datetime.datetime(2020, 11, 1)),
                    make_aware(datetime.datetime(2020, 10, 1)),
                ],
            },
        ]
        for scenario in scenarios:
            name = scenario['name']
            now = scenario['now']
            expected_months = scenario['expected_months']

            with self.subTest(scenario=name):
                with mock.patch('mtp_auth.views.timezone.localtime', return_value=now):
                    view = LoginStatsView()
                    months = view.months

                self.assertEqual(months, expected_months)

    def test_get_current_month_progress(self):
        scenarios = [
            {
                'name': 'no edge cases',
                'now': make_aware(datetime.datetime(2020, 6, 15, 12, 0)),
                'expected_progress': 0.48,
            },
            {
                'name': 'beginning of month',
                'now': make_aware(datetime.datetime(2020, 6, 1, 12, 0)),
                'expected_progress': 0.02,
            },
            {
                'name': 'end of month',
                'now': make_aware(datetime.datetime(2020, 3, 31, 10, 0)),
                'expected_progress': 0.98,
            },
            {
                'name': 'crossing year',
                'now': make_aware(datetime.datetime(2020, 12, 10, 12, 0)),
                'expected_progress': 0.31,
            },
        ]
        for scenario in scenarios:
            name = scenario['name']
            now = scenario['now']
            expected_progress = scenario['expected_progress']

            with self.subTest(scenario=name):
                with mock.patch('mtp_auth.views.timezone.localtime', return_value=now):
                    view = LoginStatsView()
                    progress = view.current_month_progress

                self.assertAlmostEqual(progress, expected_progress, delta=0.02)
