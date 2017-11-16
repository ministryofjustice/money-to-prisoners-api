from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.test import TestCase

User = get_user_model()


class DashboardTestCase(TestCase):
    fixtures = ['initial_groups.json', 'initial_types.json', 'test_prisons.json']


class CoreDashboardTestCase(DashboardTestCase):
    def test_permissions(self):
        dashboard_url = reverse('admin:dashboard')
        user_details = dict(username='a_user', password='a_user')

        user = User.objects.create_user(**user_details)
        self.client.login(**user_details)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 302)

        user.is_staff = True
        user.save()
        self.client.login(**user_details)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 302)

        view_dashboard = Permission.objects.get_by_natural_key('view_dashboard', 'transaction', 'transaction')
        user.user_permissions.add(view_dashboard)
        self.client.login(**user_details)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

        user.user_permissions.clear()
        user.is_superuser = True
        user.save()
        self.client.login(**user_details)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)
