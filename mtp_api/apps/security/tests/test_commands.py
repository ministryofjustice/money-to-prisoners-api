from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.tests.utils import make_test_users
from credit.models import Credit
from payment.tests.utils import (
    create_payments, generate_payments, generate_initial_payment_data
)
from prison.tests.utils import load_random_prisoner_locations
from security.models import SenderProfile, PrisonerProfile
from transaction.tests.utils import (
    create_transactions, generate_transactions, generate_initial_transactions_data
)


class UpdateSecurityProfilesTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, _, self.security_staff = make_test_users()
        load_random_prisoner_locations()

    def test_update_security_profiles_initial(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles')

        for sender_profile in SenderProfile.objects.all():
            credits = Credit.objects.filter(sender_profile.credit_filters)
            self.assertEqual(sum([credit.amount for credit in credits]), sender_profile.credit_total)
            self.assertEqual(len(credits), sender_profile.credit_count)

        for prisoner_profile in PrisonerProfile.objects.all():
            credits = Credit.objects.filter(prisoner_profile.credit_filters)
            self.assertEqual(sum([credit.amount for credit in credits]), prisoner_profile.credit_total)
            self.assertEqual(len(credits), prisoner_profile.credit_count)

    def test_update_security_profiles_subsequent_bank_transfer(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles')

        sender_to_update = SenderProfile.objects.filter(
            bank_transfer_details__isnull=False,
            prisoners__isnull=False
        ).first()
        bank_details = sender_to_update.bank_transfer_details.first()
        prisoner_to_update = sender_to_update.prisoners.first()

        initial_sender_credit_count = sender_to_update.credit_count
        initial_sender_credit_total = sender_to_update.credit_total
        initial_prisoner_credit_count = prisoner_to_update.credit_count
        initial_prisoner_credit_total = prisoner_to_update.credit_total

        new_transactions = generate_initial_transactions_data(
            tot=1, include_debits=False,
            include_administrative_credits=False,
            include_unidentified_credits=False, days_of_history=0
        )

        new_transactions[0]['received_at'] = timezone.now()

        new_transactions[0]['sender_name'] = bank_details.sender_name
        new_transactions[0]['sender_sort_code'] = bank_details.sender_sort_code
        new_transactions[0]['sender_account_number'] = bank_details.sender_account_number
        new_transactions[0]['sender_roll_number'] = bank_details.sender_roll_number

        new_transactions[0]['prisoner_number'] = prisoner_to_update.prisoner_number
        new_transactions[0]['prisoner_dob'] = prisoner_to_update.prisoner_dob

        create_transactions(new_transactions)
        call_command('update_security_profiles')

        sender_to_update.refresh_from_db()
        self.assertEqual(
            sender_to_update.credit_count, initial_sender_credit_count + 1
        )
        self.assertEqual(
            sender_to_update.credit_total,
            initial_sender_credit_total + new_transactions[0]['amount']
        )

        prisoner_to_update.refresh_from_db()
        self.assertEqual(
            prisoner_to_update.credit_count, initial_prisoner_credit_count + 1
        )
        self.assertEqual(
            prisoner_to_update.credit_total,
            initial_prisoner_credit_total + new_transactions[0]['amount']
        )

    def test_update_security_profiles_subsequent_card_payment(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles')

        sender_to_update = SenderProfile.objects.filter(
            debit_card_details__isnull=False,
            prisoners__isnull=False
        ).first()
        card_details = sender_to_update.debit_card_details.first()
        prisoner_to_update = sender_to_update.prisoners.first()

        initial_sender_credit_count = sender_to_update.credit_count
        initial_sender_credit_total = sender_to_update.credit_total
        initial_sender_cardholder_names = list(card_details.cardholder_names.values_list('name', flat=True))
        initial_sender_emails = list(card_details.sender_emails.values_list('email', flat=True))
        initial_prisoner_credit_count = prisoner_to_update.credit_count
        initial_prisoner_credit_total = prisoner_to_update.credit_total

        new_payments = generate_initial_payment_data(tot=1, days_of_history=0)

        new_payments[0]['received_at'] = timezone.now()

        new_payments[0]['email'] = 'dude@mtp.local'
        new_payments[0]['cardholder_name'] = 'other name'
        new_payments[0]['card_number_last_digits'] = card_details.card_number_last_digits
        new_payments[0]['card_expiry_date'] = card_details.card_expiry_date

        new_payments[0]['prisoner_number'] = prisoner_to_update.prisoner_number
        new_payments[0]['prisoner_dob'] = prisoner_to_update.prisoner_dob

        create_payments(new_payments)
        call_command('update_security_profiles')

        sender_to_update.refresh_from_db()
        self.assertEqual(
            sender_to_update.credit_count, initial_sender_credit_count + 1
        )
        self.assertEqual(
            sender_to_update.credit_total,
            initial_sender_credit_total + new_payments[0]['amount']
        )
        card_details.refresh_from_db()
        self.assertEqual(
            sorted(card_details.cardholder_names.values_list('name', flat=True)),
            sorted(initial_sender_cardholder_names + ['other name'])
        )
        self.assertEqual(
            sorted(card_details.sender_emails.values_list('email', flat=True)),
            sorted(initial_sender_emails + ['dude@mtp.local'])
        )

        prisoner_to_update.refresh_from_db()
        self.assertEqual(
            prisoner_to_update.credit_count, initial_prisoner_credit_count + 1
        )
        self.assertEqual(
            prisoner_to_update.credit_total,
            initial_prisoner_credit_total + new_payments[0]['amount']
        )
