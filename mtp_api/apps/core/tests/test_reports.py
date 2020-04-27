from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AdminReportTestCase(TestCase):
    report_urls = [
        'credit-report', 'credit-prison-report',
        'disbursement-report', 'disbursement-prison-report',
        'digital_takeup_report', 'digital_takeup_prisons',
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
