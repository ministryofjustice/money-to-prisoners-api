from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.tests.utils import make_test_users
from disbursement.tests.utils import generate_disbursements
from notification.constants import EMAIL_FREQUENCY
from notification.models import (
    Subscription, Parameter, Event, EmailNotificationPreferences
)
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
        user1 = self.security_staff[0]
        user2 = self.security_staff[1]
        start = timezone.now() - timedelta(days=2)

        # user1 subscription
        EmailNotificationPreferences.objects.create(
            user=user1, frequency=EMAIL_FREQUENCY.WEEKLY
        )
        subscription = Subscription.objects.create(
            rule='CSFREQ', user=user1, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__credit_count__gte', value=5),
            bulk=False
        )
        subscription.create_events()

        # user2 subscription
        EmailNotificationPreferences.objects.create(
            user=user2, frequency=EMAIL_FREQUENCY.WEEKLY
        )
        subscription = Subscription.objects.create(
            rule='CSFREQ', user=user2, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__credit_count__gte', value=5),
            bulk=False
        )
        subscription.create_events()

        call_command('send_notification_emails', EMAIL_FREQUENCY.WEEKLY)
        emails_sent = len(mail.outbox)
        self.assertEqual(
            emails_sent,
            Event.objects.all().values('user').distinct().count()
        )

        # test does not send additional emails without new events
        call_command('send_notification_emails', EMAIL_FREQUENCY.WEEKLY)
        self.assertEqual(
            len(mail.outbox),
            emails_sent
        )
