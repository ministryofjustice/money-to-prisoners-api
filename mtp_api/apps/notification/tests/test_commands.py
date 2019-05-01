from collections import defaultdict

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.tests.utils import make_test_users
from disbursement.tests.utils import generate_disbursements
from mtp_auth.models import PrisonUserMapping
from notification.constants import EMAIL_FREQUENCY
from notification.constants import get_notification_period
from notification.management.commands.send_notification_emails import (
    get_notification_count
)
from notification.models import Event, EmailNotificationPreferences
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

    def _check_notification_count(self, total_notifications, events):
        prisoner_profiles = defaultdict(set)
        recipient_profiles = defaultdict(set)
        sender_profiles = defaultdict(set)

        total_count = 0
        for event in events:
            if event.rule in ['NWN', 'HA']:
                total_count += 1
            elif event.rule in ['CSFREQ', 'CPNUM']:
                profile_id = event.sender_profile_event.sender_profile.id
                if profile_id not in sender_profiles[event.rule]:
                    sender_profiles[event.rule].add(profile_id)
                    total_count += 1
            elif event.rule in ['DRFREQ', 'DPNUM']:
                profile_id = event.recipient_profile_event.recipient_profile.id
                if profile_id not in recipient_profiles[event.rule]:
                    recipient_profiles[event.rule].add(profile_id)
                    total_count += 1
            elif event.rule in ['CSNUM', 'DRNUM']:
                profile_id = event.prisoner_profile_event.prisoner_profile.id
                if profile_id not in prisoner_profiles[event.rule]:
                    prisoner_profiles[event.rule].add(profile_id)
                    total_count += 1

        self.assertEqual(total_notifications, total_count)

    def test_notification_count_for_national_security(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]
        period_start, period_end = get_notification_period(EMAIL_FREQUENCY.DAILY)
        total_notifications = get_notification_count(user, period_start, period_end)
        events = Event.objects.filter(
            triggered_at__gte=period_start, triggered_at__lt=period_end
        )
        self._check_notification_count(total_notifications, events)

    def test_notification_count_for_prison_security(self):
        call_command('update_security_profiles')
        user = self.security_staff[1]
        period_start, period_end = get_notification_period(EMAIL_FREQUENCY.DAILY)
        total_notifications = get_notification_count(user, period_start, period_end)

        prisons = PrisonUserMapping.objects.get_prison_set_for_user(user)
        credit_events = Event.objects.filter(
            credit_event__isnull=False,
            credit_event__credit__prison__in=prisons,
            triggered_at__gte=period_start, triggered_at__lt=period_end
        )
        disbursement_events = Event.objects.filter(
            disbursement_event__isnull=False,
            disbursement_event__disbursement__prison__in=prisons,
            triggered_at__gte=period_start, triggered_at__lt=period_end
        )
        self._check_notification_count(
            total_notifications,
            credit_events.union(disbursement_events)
        )
