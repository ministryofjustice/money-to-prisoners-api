import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from core.forms import BasePrisonAdminReportForm, BasePeriodAdminReportForm

User = get_user_model()


class AdminReportTestCase(TestCase):
    report_urls = [
        'credit-report', 'credit-prison-report',
        'disbursement-report', 'disbursement-prison-report',
        'digital_takeup_report', 'digital_takeup_prisons',
        'user_satisfaction_report',
        'login-stats',
    ]

    def assertCanAccessReports(self):  # noqa: N802
        for report in self.report_urls:
            response = self.client.head(reverse(f'admin:{report}'))
            self.assertEqual(response.status_code, 200)

    def assertCannotAccessReports(self):  # noqa: N802
        for report in self.report_urls:
            response = self.client.head(reverse(f'admin:{report}'))
            self.assertEqual(response.status_code, 302)

    def test_unauthenticated_cannot_access_reports(self):
        self.assertCannotAccessReports()

    def test_simple_user_cannot_access_reports(self):
        simple_user = User.objects.create(
            username='simple',
            is_staff=True,
            is_superuser=False,
        )
        simple_user.set_password('simple')
        simple_user.save()
        self.client.login(
            username='simple',
            password='simple',
        )
        self.assertCannotAccessReports()
        self.client.logout()

    def test_users_can_access_reports(self):
        superuser = User.objects.create(
            username='superuser',
            is_staff=True,
            is_superuser=True,
        )
        superuser.set_password('superuser')
        superuser.save()
        self.client.login(
            username='superuser',
            password='superuser',
        )
        self.assertCanAccessReports()
        self.client.logout()

        granted_user = User.objects.create(
            username='granted',
            is_staff=True,
            is_superuser=False,
        )
        granted_user.set_password('granted')
        permission = Permission.objects.get_by_natural_key('view_dashboard', 'transaction', 'transaction')
        granted_user.user_permissions.add(permission)
        granted_user.save()
        self.client.login(
            username='granted',
            password='granted',
        )
        self.assertCanAccessReports()
        self.client.logout()


class BasePrisonAdminReportFormTestCase(SimpleTestCase):
    def test_period_date_ranges(self):
        cases = [
            (
                datetime.datetime(2020, 4, 28, 12),
                '7', datetime.date(2020, 4, 21), None,
            ),
            (
                datetime.datetime(2020, 4, 28, 12),
                'this_month', datetime.date(2020, 4, 1), None,
            ),
            (
                datetime.datetime(2020, 4, 28, 12),
                'last_month', datetime.date(2020, 3, 1), datetime.date(2020, 4, 1),
            ),
            (
                datetime.datetime(2019, 2, 25, 10),
                'this_year', datetime.date(2019, 1, 1), None,
            ),
            (
                datetime.datetime(2019, 2, 25, 10),
                'last_year', datetime.date(2018, 1, 1), datetime.date(2019, 1, 1),
            ),
            (
                datetime.datetime(2019, 2, 25, 10),
                'this_fin_year', datetime.date(2018, 4, 1), None,
            ),
            (
                datetime.datetime(2019, 2, 25, 10),
                'last_fin_year', datetime.date(2017, 4, 1), datetime.date(2018, 4, 1),
            ),
        ]
        for now, period, expected_since, expected_until in cases:
            with mock.patch('core.forms.timezone.localtime', return_value=timezone.make_aware(now)):
                form = BasePrisonAdminReportForm(data={'period': period})
                self.assertTrue(form.is_valid(), msg=form.errors)
                since, until = form.period_date_range
            self.assertEqual(since, expected_since)
            self.assertEqual(until, expected_until)


class BasePeriodAdminReportFormTestCase(SimpleTestCase):
    def make_monthly_rows(self):
        return [
            {'date': timezone.make_aware(datetime.datetime(year, month, 1, 12)), 'sample': month + year}
            for year in range(2017, 2021)
            for month in range(1, 13)
        ]

    def test_period_formatting(self):
        cases = {
            'quarterly': [
                'Q1 2017', 'Q2 2017', 'Q3 2017', 'Q4 2017', 'Q1 2018', 'Q2 2018', 'Q3 2018', 'Q4 2018',
                'Q1 2019', 'Q2 2019', 'Q3 2019', 'Q4 2019', 'Q1 2020', 'Q2 2020', 'Q3 2020', 'Q4 2020',
            ],
            'yearly': ['2017', '2018', '2019', '2020'],
            'financial': [
                'April 2016 to April 2017', 'April 2017 to April 2018', 'April 2018 to April 2019',
                'April 2019 to April 2020', 'April 2020 to April 2021',
            ],
        }
        for period, expected_periods in cases.items():
            form = BasePeriodAdminReportForm(data={'period': period})
            self.assertTrue(form.is_valid(), msg=form.errors)
            period_formatter = form.period_formatter
            period_rows = form.group_months_into_periods(self.make_monthly_rows())
            formatted_periods = [period_formatter(row['date']) for row in period_rows]
            self.assertListEqual(formatted_periods, expected_periods)

    def test_period_grouping(self):
        cases = {
            'quarterly': [
                6057, 6066, 6075, 6084, 6060, 6069, 6078, 6087, 6063, 6072, 6081, 6090, 6066, 6075, 6084, 6093,
            ],
            'yearly': [
                6057 + 6066 + 6075 + 6084,
                6060 + 6069 + 6078 + 6087,
                6063 + 6072 + 6081 + 6090,
                6066 + 6075 + 6084 + 6093,
            ],
            'financial': [
                6057,
                6066 + 6075 + 6084 + 6060,
                6069 + 6078 + 6087 + 6063,
                6072 + 6081 + 6090 + 6066,
                6075 + 6084 + 6093,
            ],
        }
        for period, expected_periods in cases.items():
            form = BasePeriodAdminReportForm(data={'period': period})
            self.assertTrue(form.is_valid(), msg=form.errors)
            period_rows = form.group_months_into_periods(self.make_monthly_rows())
            period_samples = [row['sample'] for row in period_rows]
            self.assertListEqual(period_samples, expected_periods)

    def test_current_period(self):
        cases = [
            ('monthly', datetime.datetime(2020, 4, 28, 12), datetime.date(2020, 4, 1)),
            ('quarterly', datetime.datetime(2020, 4, 28, 12), datetime.date(2020, 4, 1)),
            ('yearly', datetime.datetime(2020, 4, 28, 12), datetime.date(2020, 1, 1)),
            ('financial', datetime.datetime(2020, 4, 28, 12), datetime.date(2020, 4, 1)),
            ('monthly', datetime.datetime(2019, 2, 25, 10), datetime.date(2019, 2, 1)),
            ('quarterly', datetime.datetime(2019, 2, 25, 10), datetime.date(2019, 1, 1)),
            ('yearly', datetime.datetime(2019, 2, 25, 10), datetime.date(2019, 1, 1)),
            ('financial', datetime.datetime(2019, 2, 25, 10), datetime.date(2018, 4, 1)),
        ]
        for period, now, expected_current_period in cases:
            with mock.patch('core.forms.timezone.localtime', return_value=timezone.make_aware(now)):
                form = BasePeriodAdminReportForm(data={'period': period})
                self.assertTrue(form.is_valid(), msg=form.errors)
                current_period = form.current_period
                self.assertEqual(current_period.time(), datetime.time.min)
                self.assertEqual(current_period.date(), expected_current_period)
