import csv
import datetime
import tempfile
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.test.utils import captured_stdout

from core.tests.utils import make_test_users
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from payment.constants import PAYMENT_STATUS
from payment.models import Payment
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations


class DumpForAPTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def basic_setup(self):
        make_test_users()
        load_random_prisoner_locations()

    def test_invalid_arguments(self):
        with self.assertRaises(CommandError, msg='Should be missing type and path'):
            call_command('dump_for_ap')
        with self.assertRaises(CommandError, msg='Type should be incorrect'):
            call_command('dump_for_ap', 'notifications', '-')
        with self.assertRaises(CommandError, msg='Should be missing path'):
            call_command('dump_for_ap', 'credits')
        with self.assertRaises(CommandError, msg='After should be incorrect'):
            call_command('dump_for_ap', 'credits', '-', after='tomorrow')
        with self.assertRaises(CommandError, msg='Date order should be incorrect'):
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
        with tempfile.NamedTemporaryFile() as csv_file:
            call_command('dump_for_ap', 'credits', csv_file.name)
            lines = open(csv_file.name).read().splitlines()
        self.assertEqual(len(lines), 1)

    def test_credits_dump_for_ap(self):
        self.basic_setup()
        generate_payments(payment_batch=20, days_of_history=2)

        with tempfile.NamedTemporaryFile(mode='rt') as export_file:
            call_command('dump_for_ap', 'credits', export_file.name)

            csv_reader = csv.DictReader(export_file)
            credit_ids = []
            for record in csv_reader:
                credit_ids.append(int(record['Internal ID']))

        completed_payments = Payment.objects.exclude(
            status__in=(
                PAYMENT_STATUS.PENDING,
                PAYMENT_STATUS.REJECTED,
                PAYMENT_STATUS.EXPIRED,
            )
        )
        expected_credit_ids = sorted(payment.credit_id for payment in completed_payments)
        self.assertListEqual(credit_ids, expected_credit_ids)

    def test_disbursements_dump_for_ap(self):
        self.basic_setup()
        generate_disbursements(disbursement_batch=20, days_of_history=2)

        with tempfile.NamedTemporaryFile(mode='rt') as export_file:
            call_command('dump_for_ap', 'disbursements', export_file.name)

            csv_reader = csv.DictReader(export_file)
            disbursement_ids = []
            for record in csv_reader:
                disbursement_ids.append(int(record['Internal ID']))

        expected_disbursement_ids = sorted(Disbursement.objects.values_list('pk', flat=True))
        self.assertListEqual(disbursement_ids, expected_disbursement_ids)
