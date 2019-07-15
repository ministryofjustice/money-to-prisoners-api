import datetime

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from model_mommy import mommy

from core.tests.utils import make_test_users
from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from notification.constants import EMAIL_FREQUENCY
from notification.management.commands.send_notification_emails import get_events, group_events, EMAILS_STARTED_FLAG
from notification.models import Event, EmailNotificationPreferences
from payment.models import Payment
from payment.tests.utils import generate_payments
from prison.models import PrisonerLocation
from prison.tests.utils import load_random_prisoner_locations
from security.models import PrisonerProfile, SenderProfile, DebitCardSenderDetails


class SendNotificationEmailsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()
        generate_payments(payment_batch=20, days_of_history=2)
        generate_disbursements(disbursement_batch=20, days_of_history=2)

    @override_settings(ENVIRONMENT='prod')
    def test_does_not_send_email_notifications_for_no_events(self):
        user = self.security_staff[0]
        user.flags.create(name=EMAILS_STARTED_FLAG)
        EmailNotificationPreferences(user=user, frequency=EMAIL_FREQUENCY.DAILY).save()
        call_command('send_notification_emails')

        self.assertFalse(Event.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ENVIRONMENT='prod')
    def test_does_not_send_email_notifications_for_no_monitoring(self):
        user = self.security_staff[0]
        user.flags.create(name=EMAILS_STARTED_FLAG)
        EmailNotificationPreferences(user=user, frequency=EMAIL_FREQUENCY.DAILY).save()
        call_command('update_security_profiles')
        call_command('send_notification_emails')

        self.assertFalse(Event.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ENVIRONMENT='prod')
    def test_sends_first_email_not_monitoring(self):
        user = self.security_staff[0]
        EmailNotificationPreferences(user=user, frequency=EMAIL_FREQUENCY.DAILY).save()
        call_command('update_security_profiles')
        call_command('send_notification_emails')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[-1].subject, 'New helpful ways to get the best from the intelligence tool')
        self.assertTrue(user.flags.filter(name=EMAILS_STARTED_FLAG).exists())

    def create_profiles_but_unlink_objects(self):
        call_command('update_security_profiles')
        Credit.objects.update(sender_profile=None, prisoner_profile=None)
        Disbursement.objects.update(recipient_profile=None, prisoner_profile=None)
        # NB: profiles will have incorrect counts and totals

    @override_settings(ENVIRONMENT='prod')
    def test_sends_first_email_with_events(self):
        user = self.security_staff[0]
        EmailNotificationPreferences(user=user, frequency=EMAIL_FREQUENCY.DAILY).save()
        self.create_profiles_but_unlink_objects()
        for profile in PrisonerProfile.objects.all():
            profile.monitoring_users.add(user)
        call_command('update_security_profiles')
        call_command('send_notification_emails')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[-1].subject, 'New notification feature added to intelligence tool')
        self.assertTrue(user.flags.filter(name=EMAILS_STARTED_FLAG).exists())
        yesterday = timezone.now() - datetime.timedelta(days=1)
        yesterday = yesterday.date()
        transaction_count = Event.objects.filter(triggered_at__date=yesterday, user=user).count()
        self.assertIn(f'You have {transaction_count} notification', mail.outbox[-1].body)

    @override_settings(ENVIRONMENT='prod')
    def test_sends_subsequent_email_with_events(self):
        user = self.security_staff[0]
        user.flags.create(name=EMAILS_STARTED_FLAG)
        EmailNotificationPreferences(user=user, frequency=EMAIL_FREQUENCY.DAILY).save()
        self.create_profiles_but_unlink_objects()
        for profile in DebitCardSenderDetails.objects.all():
            profile.monitoring_users.add(user)
        call_command('update_security_profiles')
        call_command('send_notification_emails')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[-1].subject, 'Your new intelligence tool notifications')
        self.assertTrue(user.flags.filter(name=EMAILS_STARTED_FLAG).exists())
        yesterday = timezone.now() - datetime.timedelta(days=1)
        yesterday = yesterday.date()
        transaction_count = Event.objects.filter(triggered_at__date=yesterday, user=user).count()
        self.assertIn(f'You have {transaction_count} notification', mail.outbox[-1].body)

    def test_profile_grouping(self):
        user = self.security_staff[0]
        call_command('update_security_profiles')
        for profile in PrisonerProfile.objects.all():
            profile.monitoring_users.add(user)
        for profile in DebitCardSenderDetails.objects.all():
            profile.monitoring_users.add(user)

        period_start = timezone.make_aware(datetime.datetime.combine(timezone.now(), datetime.time.min))
        period_start -= datetime.timedelta(days=7)
        period_end = period_start + datetime.timedelta(days=1)
        events = get_events(period_start, period_end)
        self.assertFalse(events.exists())

        prisoner_profile_1, prisoner_profile_2 = PrisonerProfile.objects.all()[:2]
        sender_profile_1, sender_profile_2 = SenderProfile.objects.filter(debit_card_details__isnull=False)[:2]
        debit_card_1 = sender_profile_1.debit_card_details.first()
        debit_card_2 = sender_profile_2.debit_card_details.first()
        credit = mommy.make(
            Credit,
            received_at=period_start, amount=100,
            prisoner_number=prisoner_profile_1.prisoner_number, prisoner_name=prisoner_profile_1.prisoner_name,
            prison=PrisonerLocation.objects.get(prisoner_number=prisoner_profile_1.prisoner_number).prison,
            resolution=CREDIT_RESOLUTION.CREDITED, reconciled=True, private_estate_batch=None,
            prisoner_profile=None, sender_profile=None,
        )
        mommy.make(
            Payment,
            credit=credit,
            card_number_last_digits=debit_card_1.card_number_last_digits,
            card_expiry_date=debit_card_1.card_expiry_date,
            billing_address=debit_card_1.billing_addresses.first(),
        )
        credit = mommy.make(
            Credit,
            received_at=period_start, amount=200,
            prisoner_number=prisoner_profile_2.prisoner_number, prisoner_name=prisoner_profile_2.prisoner_name,
            prison=PrisonerLocation.objects.get(prisoner_number=prisoner_profile_2.prisoner_number).prison,
            resolution=CREDIT_RESOLUTION.CREDITED, reconciled=True, private_estate_batch=None,
            prisoner_profile=None, sender_profile=None,
        )
        mommy.make(
            Payment,
            credit=credit,
            card_number_last_digits=debit_card_2.card_number_last_digits,
            card_expiry_date=debit_card_2.card_expiry_date,
            billing_address=debit_card_2.billing_addresses.first(),
        )

        call_command('update_security_profiles')

        events = get_events(period_start, period_end)
        event_group = group_events(events, user)
        self.assertEqual(event_group['transaction_count'], 4)
        self.assertEqual(len(event_group['senders']), 2)
        self.assertEqual(len(event_group['prisoners']), 2)
