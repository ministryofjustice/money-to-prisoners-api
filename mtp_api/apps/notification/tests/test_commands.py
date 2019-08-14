import csv
import datetime
import io
from unittest import mock
import zipfile

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from model_mommy import mommy

from core.tests.utils import make_test_users
from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from notification.constants import EMAIL_FREQUENCY
from notification.management.commands.send_notification_emails import (
    EMAILS_STARTED_FLAG,
    get_events, group_events, summarise_group,
)
from notification.management.commands.send_notification_report import (
    Command as ReportCommand, CreditSerialiser, DisbursementSerialiser,
)
from notification.models import Event, EmailNotificationPreferences
from notification.rules import RULES
from payment.models import Payment
from payment.tests.utils import generate_payments
from prison.models import PrisonerLocation
from prison.tests.utils import load_random_prisoner_locations
from security.models import PrisonerProfile, SenderProfile, DebitCardSenderDetails


class NotificationBaseTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def create_profiles_but_unlink_objects(self):
        call_command('update_security_profiles')
        Credit.objects.update(sender_profile=None, prisoner_profile=None)
        Disbursement.objects.update(recipient_profile=None, prisoner_profile=None)
        # NB: profiles will have incorrect counts and totals


class SendNotificationEmailsTestCase(NotificationBaseTestCase):
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
        self.assertIsNone(EmailNotificationPreferences.objects.get(user=user).last_sent_at)

    @override_settings(ENVIRONMENT='prod')
    def test_does_not_send_email_notifications_for_no_monitoring(self):
        user = self.security_staff[0]
        user.flags.create(name=EMAILS_STARTED_FLAG)
        EmailNotificationPreferences(user=user, frequency=EMAIL_FREQUENCY.DAILY).save()
        call_command('update_security_profiles')
        call_command('send_notification_emails')

        self.assertFalse(Event.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(EmailNotificationPreferences.objects.get(user=user).last_sent_at)

    @override_settings(ENVIRONMENT='prod')
    def test_sends_first_email_not_monitoring(self):
        user = self.security_staff[0]
        EmailNotificationPreferences(user=user, frequency=EMAIL_FREQUENCY.DAILY).save()
        call_command('update_security_profiles')
        call_command('send_notification_emails')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[-1].subject, 'New helpful ways to get the best from the intelligence tool')
        self.assertTrue(user.flags.filter(name=EMAILS_STARTED_FLAG).exists())
        self.assertIsNotNone(EmailNotificationPreferences.objects.get(user=user).last_sent_at)

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
        self.assertIsNotNone(EmailNotificationPreferences.objects.get(user=user).last_sent_at)

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
        self.assertIsNotNone(EmailNotificationPreferences.objects.get(user=user).last_sent_at)

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
        event_group = summarise_group(group_events(events, user))
        self.assertEqual(event_group['transaction_count'], 4)
        self.assertEqual(len(event_group['senders']), 2)
        self.assertEqual(len(event_group['prisoners']), 2)

    @override_settings(ENVIRONMENT='prod')
    @mock.patch('notification.management.commands.send_notification_emails.timezone')
    def test_does_not_send_email_if_already_sent_today(self, mock_timezone):
        today_now = timezone.now()
        today_date = today_now.date()
        yesterday_now = today_now - datetime.timedelta(days=1)
        yesterday_date = yesterday_now.date()

        user = self.security_staff[0]
        user.flags.create(name=EMAILS_STARTED_FLAG)
        EmailNotificationPreferences(user=user, frequency=EMAIL_FREQUENCY.DAILY).save()
        self.create_profiles_but_unlink_objects()
        for profile in DebitCardSenderDetails.objects.all():
            profile.monitoring_users.add(user)
        call_command('update_security_profiles')
        self.assertTrue(Event.objects.filter(triggered_at__date=yesterday_date).exists())
        self.assertTrue(Event.objects.filter(triggered_at__date=today_date).exists())

        # pretend it's yesterday
        mock_timezone.now.return_value = yesterday_now
        call_command('send_notification_emails')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailNotificationPreferences.objects.get(user=user).last_sent_at, yesterday_date)

        call_command('send_notification_emails')
        self.assertEqual(len(mail.outbox), 1)

        # now check today
        mock_timezone.now.return_value = today_now
        call_command('send_notification_emails')
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(EmailNotificationPreferences.objects.get(user=user).last_sent_at, today_date)

        call_command('send_notification_emails')
        self.assertEqual(len(mail.outbox), 2)


@override_settings(ENVIRONMENT='prod')
class SendNotificationReportTestCase(NotificationBaseTestCase):
    def make_2days_of_random_models(self):
        test_users = make_test_users()
        load_random_prisoner_locations()
        generate_payments(payment_batch=20, days_of_history=2)
        generate_disbursements(disbursement_batch=20, days_of_history=2)
        return test_users['security_staff']

    def test_invalid_parameters(self):
        with self.assertRaises(CommandError, msg='Email address should be invalid'):
            call_command('send_notification_report', 'admin')
        with self.assertRaises(CommandError, msg='Email address should be invalid'):
            call_command('send_notification_report', 'admin@mtp.local', 'admin')
        with self.assertRaises(CommandError, msg='Date should be invalid'):
            call_command('send_notification_report', 'admin@mtp.local', since='yesterday')
        with self.assertRaises(CommandError, msg='Dates should be invalid'):
            call_command('send_notification_report', 'admin@mtp.local', since='2019-08-01', until='2019-08-01')
        with self.assertRaises(CommandError, msg='Dates should be invalid'):
            call_command('send_notification_report', 'admin@mtp.local', since='2019-08-02', until='2019-08-01')
        with self.assertRaises(CommandError, msg='Date span should be invalid'):
            call_command('send_notification_report', 'admin@mtp.local', since='2019-07-01', until='2019-08-01')
        with self.assertRaises((CommandError, KeyError), msg='Rules should be invalid'):
            call_command('send_notification_report', 'admin@mtp.local', rules=['abc'])
        self.assertEqual(len(mail.outbox), 0)

    def test_date_ranges(self):
        command = ReportCommand()
        command.generate_reports = mock.MagicMock()

        call_command(command, 'admin@mtp.local', since='2019-08-01', until='2019-08-02')
        period_start, period_end, _rules, _emails = command.generate_reports.call_args[0]
        self.assertEqual(period_start.date(), datetime.date(2019, 8, 1))
        self.assertEqual(period_end.date(), datetime.date(2019, 8, 2))

        today = timezone.localtime(timezone.now()).date()
        yesterday = today - datetime.timedelta(days=1)

        call_command(command, 'admin@mtp.local', since=yesterday.isoformat())
        period_start, period_end, _rules, _emails = command.generate_reports.call_args[0]
        self.assertEqual(period_start.date(), yesterday)
        self.assertEqual(period_end.date(), today)

        call_command(command, 'admin@mtp.local', until=yesterday.isoformat())
        period_start, period_end, _rules, _emails = command.generate_reports.call_args[0]
        self.assertEqual(period_start.date(), yesterday - datetime.timedelta(days=1))
        self.assertEqual(period_end.date(), yesterday)

        call_command(command, 'admin@mtp.local')
        period_start, period_end, _rules, _emails = command.generate_reports.call_args[0]
        self.assertEqual(period_end.date() - datetime.timedelta(days=7), period_start.date())

    def test_empty_report(self):
        call_command('send_notification_report', 'admin@mtp.local')
        self.assertEqual(len(mail.outbox), 0)

    def test_reports_generated(self):
        self.make_2days_of_random_models()

        # move 1 credit and 1 disbursement to a past date and make them appear in report (HA and NWN)
        credit = Credit.objects.all().order_by('?').first()
        credit.received_at -= datetime.timedelta(days=7)
        credit.amount = 12501
        credit.save()
        disbursement = Disbursement.objects.sent().order_by('?').first()
        disbursement.created = credit.received_at
        disbursement.amount = 13602
        disbursement.save()

        call_command('update_security_profiles')

        # generate reports
        report_date = credit.received_at.date()
        since = report_date.strftime('%Y-%m-%d')
        until = (report_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        call_command('send_notification_report', 'admin@mtp.local', since=since, until=until)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn(report_date.strftime('%d %b %Y'), email.body)
        self.assertEqual(len(email.attachments), 1)
        _, contents, *_ = email.attachments[0]
        contents = zipfile.ZipFile(io.BytesIO(contents))

        credit_files = {'credits-HA.csv', 'credits-NWN.csv'}
        disbursement_files = {'disbursements-HA.csv', 'disbursements-NWN.csv'}
        self.assertSetEqual(
            set(contents.namelist()),
            credit_files | disbursement_files
        )
        for file in credit_files:
            file = contents.read(file).decode()
            self.assertEqual(len(file.splitlines()), 2)
            self.assertIn('£125.01', file)
            self.assertIn(credit.prisoner_name, file)
        for file in disbursement_files:
            file = contents.read(file).decode()
            self.assertEqual(len(file.splitlines()), 2)
            self.assertIn('£136.02', file)
            self.assertIn(disbursement.recipient_address, file)
