import csv
import datetime
import io
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.test.utils import captured_stdout
from django.utils import timezone
from model_mommy import mommy

from core.tests.utils import make_test_users
from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from payment.constants import PAYMENT_STATUS
from payment.models import Payment
from payment.tests.utils import generate_payments
from prison.models import PrisonerLocation
from prison.tests.utils import load_random_prisoner_locations
from security.models import PrisonerProfile, SenderProfile, DebitCardSenderDetails


class DumpForAPTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def basic_setup(self):
        make_test_users()
        load_random_prisoner_locations()

    def test_invalid_arguments(self):
        with self.assertRaises(CommandError):
            call_command('dump_for_ap')
        with self.assertRaises(CommandError):
            call_command('dump_for_ap', 'notifications')
        with self.assertRaises(CommandError):
            call_command('dump_for_ap', 'credits')
        with self.assertRaises(CommandError):
            call_command('dump_for_ap', 'credits', '-', after='tomorrow')
        with self.assertRaises(CommandError):
            call_command('dump_for_ap', 'credits', '-', before='2019-08-01', after='2019-09-01')

    @mock.patch('core.management.commands.dump_for_ap.Serialiser.get_modified_records')
    def test_valid_arguments(self, mocked_get_modified_records):
        with captured_stdout():
            call_command('dump_for_ap', 'credits', '-', after='2019-09-26')
        after, *_ = mocked_get_modified_records.call_args[0]
        self.assertEqual(after.date(), datetime.date(2019, 9, 26))

        with captured_stdout():
            call_command('dump_for_ap', 'disbursements', '-', before='2019-09-01', after='2019-08-01')
        after, before, *_ = mocked_get_modified_records.call_args[0]
        self.assertEqual(after.date(), datetime.date(2019, 8, 1))
        self.assertEqual(before.date(), datetime.date(2019, 9, 1))

    def test_empty_results(self):
        with captured_stdout() as stdout:
            call_command('dump_for_ap', 'credits', '-')
        stdout = stdout.getvalue().strip()
        lines = stdout.splitlines()
        self.assertEqual(len(lines), 1)

    def test_credits_dump_for_ap(self):
        self.basic_setup()
        generate_payments(payment_batch=20, days_of_history=2)
        with captured_stdout() as stdout:
            call_command('dump_for_ap', 'credits', '-')
        stdout.seek(0)
        csv_reader = csv.DictReader(stdout)
        credit_ids = sorted(int(record['Internal ID']) for record in csv_reader)
        completed_payments = Payment.objects.exclude(status=PAYMENT_STATUS.PENDING)
        expected_credit_ids = sorted(payment.credit_id for payment in completed_payments)
        self.assertListEqual(credit_ids, expected_credit_ids)

    def test_disbursements_dump_for_ap(self):
        self.basic_setup()
        generate_disbursements(disbursement_batch=20, days_of_history=2)
        with captured_stdout() as stdout:
            call_command('dump_for_ap', 'disbursements', '-')
        stdout.seek(0)
        csv_reader = csv.DictReader(stdout)
        disbursement_ids = sorted(int(record['Internal ID']) for record in csv_reader)
        expected_disbursement_ids = sorted(Disbursement.objects.values_list('pk', flat=True))
        self.assertListEqual(disbursement_ids, expected_disbursement_ids)
