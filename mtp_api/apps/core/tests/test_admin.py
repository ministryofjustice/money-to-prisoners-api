from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.test import TestCase
from mtp_common.test_utils import silence_logger


class RecreateTestDataViewTestCase(TestCase):
    @property
    def url(self):
        return reverse('admin:recreate_test_data')

    def make_superuser(self, log_into_client=False):
        superuser = get_user_model().objects.create(
            username='superuser',
            is_staff=True,
            is_superuser=True,
        )
        superuser.set_password('superuser')
        superuser.save()
        if log_into_client:
            self.assertTrue(self.client.login(
                username='superuser',
                password='superuser',
            ))
        return superuser

    def test_anonymous_access_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_unauthorised_access_denied(self):
        call_command('load_test_data', verbosity=0)
        self.assertTrue(self.client.login(
            username='test-prison-1',
            password='test-prison-1',
        ))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_superadmin_access_allowed(self):
        self.make_superuser(log_into_client=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h1>Recreate test data</h1>', html=True)

    def test_data_management_command_runs(self):
        from core.management.commands.load_test_data import Command

        self.make_superuser(log_into_client=True)
        with mock.patch.object(Command, 'handle') as method:
            with silence_logger():
                response = self.client.post(self.url, data={
                    'scenario': 'random',
                    'number_of_transactions': '50',
                    'number_of_payments': '50',
                    'number_of_prisoners': '50',
                    'days_of_history': '7',
                })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(method.call_count, 1)
            expected_options_subset = {
                'protect_superusers': True,
                'protect_usernames': ['transaction-uploader'],
                'protect_credits': False,
                'no_color': True,
                'credits': 'random',
                'prisons': ['sample'],
                'number_of_transactions': 50,
                'number_of_payments': 50,
                'number_of_prisoners': 50,
                'days_of_history': 7
            }
            options = method.call_args[1]
            options_subset = {
                k: v
                for k, v in options.items()
                if k in expected_options_subset.keys()
            }
            self.assertDictEqual(options_subset, expected_options_subset)
