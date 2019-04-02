from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.tests.utils import make_test_users
from disbursement.tests.utils import generate_disbursements
from notification.constants import EMAIL_FREQUENCY
from notification.models import Event, EmailNotificationPreferences
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.constants import TIME_PERIOD


class SendNotificationEmailsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()
        generate_payments(payment_batch=200, days_of_history=3)
        generate_disbursements(disbursement_batch=200, days_of_history=3)
        call_command('update_security_profiles')

    @override_settings(ENVIRONMENT='prod')
    def test_send_email_notifications(self):
        pass
