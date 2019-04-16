from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.tests.utils import make_test_users
from disbursement.tests.utils import generate_disbursements
from notification.constants import EMAIL_FREQUENCY
from notification.models import EmailNotificationPreferences
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations


class SendNotificationEmailsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()
        generate_payments(payment_batch=200, days_of_history=3)
        generate_disbursements(disbursement_batch=200, days_of_history=3)

    @override_settings(ENVIRONMENT='prod')
    def test_send_email_notifications(self):
        call_command('update_security_profiles')
        EmailNotificationPreferences(
            user=self.security_staff[0], frequency=EMAIL_FREQUENCY.DAILY
        ).save()
        call_command('send_notification_emails', frequency=EMAIL_FREQUENCY.DAILY)

        self.assertEqual(len(mail.outbox), 1)

    @override_settings(ENVIRONMENT='prod')
    def test_does_not_send_email_notifications_for_no_events(self):
        EmailNotificationPreferences(
            user=self.security_staff[0], frequency=EMAIL_FREQUENCY.DAILY
        ).save()
        call_command('send_notification_emails', frequency=EMAIL_FREQUENCY.DAILY)

        self.assertEqual(len(mail.outbox), 0)
