from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.tests.utils import make_test_users
from credit.models import Credit
from disbursement.constants import DISBURSEMENT_METHOD, DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from disbursement.tests.utils import (
    generate_disbursements, generate_initial_disbursement_data,
    create_disbursements
)
from payment.constants import PAYMENT_STATUS
from payment.tests.utils import (
    create_payments, generate_payments, generate_initial_payment_data
)
from prison.models import PrisonerLocation, Prison
from prison.tests.utils import load_random_prisoner_locations
from security.constants import TIME_PERIOD
from security.models import SenderProfile, PrisonerProfile, RecipientProfile
from transaction.tests.utils import (
    create_transactions, generate_transactions, generate_initial_transactions_data
)


class UpdateSecurityProfilesTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()

    def test_update_security_profiles_initial(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        call_command('update_security_profiles', verbosity=0)

        for sender_profile in SenderProfile.objects.all():
            credits = Credit.objects.filter(sender_profile.credit_filters)
            self.assertEqual(
                sum([credit.amount for credit in credits]),
                sender_profile.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_total
            )
            self.assertEqual(
                len(credits),
                sender_profile.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_count
            )

        for recipient_profile in RecipientProfile.objects.filter(
            bank_transfer_details__isnull=False
        ):
            disbursements = Disbursement.objects.filter(recipient_profile.disbursement_filters)
            self.assertEqual(
                sum([disbursement.amount for disbursement in disbursements]),
                recipient_profile.totals.get(time_period=TIME_PERIOD.ALL_TIME).disbursement_total
            )
            self.assertEqual(
                len(disbursements),
                recipient_profile.totals.get(time_period=TIME_PERIOD.ALL_TIME).disbursement_count
            )

        for prisoner_profile in PrisonerProfile.objects.all():
            if prisoner_profile.credits.count():
                self.assertTrue(prisoner_profile.single_offender_id)

            credits = Credit.objects.filter(prisoner_profile.credit_filters)
            self.assertEqual(
                sum([credit.amount for credit in credits]),
                prisoner_profile.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_total
            )
            self.assertEqual(
                len(credits),
                prisoner_profile.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_count
            )

            disbursements = Disbursement.objects.filter(prisoner_profile.disbursement_filters)
            self.assertEqual(
                sum([disbursement.amount for disbursement in disbursements]),
                prisoner_profile.totals.get(time_period=TIME_PERIOD.ALL_TIME).disbursement_total
            )
            self.assertEqual(
                len(disbursements),
                prisoner_profile.totals.get(time_period=TIME_PERIOD.ALL_TIME).disbursement_count
            )

    def test_update_security_profiles_subsequent_bank_transfer(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles', verbosity=0)

        sender_to_update = SenderProfile.objects.filter(
            bank_transfer_details__isnull=False,
            prisoners__isnull=False
        ).first()
        bank_details = sender_to_update.bank_transfer_details.first()
        prisoner_to_update = sender_to_update.prisoners.first()

        initial_sender_credit_count = sender_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).credit_count
        initial_sender_credit_total = sender_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).credit_total
        initial_prisoner_credit_count = prisoner_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).credit_count
        initial_prisoner_credit_total = prisoner_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).credit_total

        new_transactions = generate_initial_transactions_data(
            tot=1, include_debits=False,
            include_administrative_credits=False,
            include_unidentified_credits=False, days_of_history=0
        )

        new_transactions[0]['received_at'] = timezone.now()

        new_transactions[0]['sender_name'] = bank_details.sender_name
        new_transactions[0]['sender_sort_code'] = bank_details.sender_bank_account.sort_code
        new_transactions[0]['sender_account_number'] = bank_details.sender_bank_account.account_number
        new_transactions[0]['sender_roll_number'] = bank_details.sender_bank_account.roll_number

        new_transactions[0]['prisoner_number'] = prisoner_to_update.prisoner_number
        new_transactions[0]['prisoner_dob'] = prisoner_to_update.prisoner_dob

        create_transactions(new_transactions)
        call_command('update_security_profiles', verbosity=0)

        sender_to_update.refresh_from_db()
        self.assertEqual(
            sender_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_count,
            initial_sender_credit_count + 1
        )
        self.assertEqual(
            sender_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_total,
            initial_sender_credit_total + new_transactions[0]['amount']
        )

        prisoner_to_update.refresh_from_db()
        self.assertEqual(
            prisoner_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_count,
            initial_prisoner_credit_count + 1
        )
        self.assertEqual(
            prisoner_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_total,
            initial_prisoner_credit_total + new_transactions[0]['amount']
        )

    def test_update_security_profiles_subsequent_card_payment(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles', verbosity=0)

        sender_to_update = SenderProfile.objects.filter(
            debit_card_details__isnull=False,
            prisoners__isnull=False
        ).first()
        card_details = sender_to_update.debit_card_details.first()
        prisoner_to_update = sender_to_update.prisoners.first()

        initial_sender_credit_count = sender_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).credit_count
        initial_sender_credit_total = sender_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).credit_total
        initial_sender_cardholder_names = list(card_details.cardholder_names.values_list('name', flat=True))
        initial_sender_emails = list(card_details.sender_emails.values_list('email', flat=True))
        initial_prisoner_credit_count = prisoner_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).credit_count
        initial_prisoner_credit_total = prisoner_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).credit_total

        new_payments = generate_initial_payment_data(tot=1, days_of_history=0)

        new_payments[0]['created'] = timezone.now()

        new_payments[0]['email'] = 'dude@mtp.local'
        new_payments[0]['cardholder_name'] = 'other name'
        new_payments[0]['card_number_last_digits'] = card_details.card_number_last_digits
        new_payments[0]['card_expiry_date'] = card_details.card_expiry_date
        new_payments[0]['billing_address']['postcode'] = card_details.postcode

        new_payments[0]['prisoner_number'] = prisoner_to_update.prisoner_number
        new_payments[0]['prisoner_dob'] = prisoner_to_update.prisoner_dob

        create_payments(new_payments)
        call_command('update_security_profiles', verbosity=0)

        sender_to_update.refresh_from_db()
        self.assertEqual(
            sender_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_count,
            initial_sender_credit_count + 1
        )
        self.assertEqual(
            sender_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_total,
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
            prisoner_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_count,
            initial_prisoner_credit_count + 1
        )
        self.assertEqual(
            prisoner_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).credit_total,
            initial_prisoner_credit_total + new_payments[0]['amount']
        )

    def test_update_security_profiles_subsequent_disbursement(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        call_command('update_security_profiles', verbosity=0)

        recipient_to_update = RecipientProfile.objects.filter(
            bank_transfer_details__isnull=False,
            prisoners__isnull=False
        ).first()
        bank_details = recipient_to_update.bank_transfer_details.first()
        prisoner_to_update = recipient_to_update.prisoners.first()

        initial_recipient_disbursement_count = recipient_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).disbursement_count
        initial_recipient_disbursement_total = recipient_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).disbursement_total
        initial_prisoner_disbursement_count = prisoner_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).disbursement_count
        initial_prisoner_disbursement_total = prisoner_to_update.totals.get(
            time_period=TIME_PERIOD.ALL_TIME).disbursement_total

        new_disbursements = generate_initial_disbursement_data(
            tot=1, days_of_history=0
        )

        new_disbursements[0]['method'] = DISBURSEMENT_METHOD.BANK_TRANSFER
        new_disbursements[0]['sort_code'] = bank_details.recipient_bank_account.sort_code
        new_disbursements[0]['account_number'] = bank_details.recipient_bank_account.account_number
        new_disbursements[0]['roll_number'] = bank_details.recipient_bank_account.roll_number

        new_disbursements[0]['prisoner_number'] = prisoner_to_update.prisoner_number
        new_disbursements[0]['prisoner_name'] = prisoner_to_update.prisoner_name
        new_disbursements[0]['resolution'] = DISBURSEMENT_RESOLUTION.SENT

        create_disbursements(new_disbursements)
        call_command('update_security_profiles', verbosity=0)

        recipient_to_update.refresh_from_db()
        self.assertEqual(
            recipient_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).disbursement_count,
            initial_recipient_disbursement_count + 1
        )
        self.assertEqual(
            recipient_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).disbursement_total,
            initial_recipient_disbursement_total + new_disbursements[0]['amount']
        )

        prisoner_to_update.refresh_from_db()
        self.assertEqual(
            prisoner_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).disbursement_count,
            initial_prisoner_disbursement_count + 1
        )
        self.assertEqual(
            prisoner_to_update.totals.get(time_period=TIME_PERIOD.ALL_TIME).disbursement_total,
            initial_prisoner_disbursement_total + new_disbursements[0]['amount']
        )

    def test_update_prisoner_profiles(self):
        payments = generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles', verbosity=0)

        valid_payments = filter(lambda payment: payment.status == PAYMENT_STATUS.TAKEN and payment.credit.prison,
                                payments)
        prisoner_numbers = set(payment.prisoner_number for payment in valid_payments)
        self.assertEqual(PrisonerProfile.objects.all().count(), len(prisoner_numbers))

        sender_profile = SenderProfile.objects.filter(
            debit_card_details__isnull=False,
            prisoners__isnull=False,
        ).first()
        debit_card_details = sender_profile.debit_card_details.first()
        prisoner_profile = PrisonerProfile.objects.first()

        new_payments = generate_initial_payment_data(tot=1, days_of_history=0)

        new_payments[0]['created'] = timezone.now()

        new_payments[0]['email'] = 'doe@mtp.local'
        new_payments[0]['cardholder_name'] = 'other name'
        new_payments[0]['card_number_last_digits'] = debit_card_details.card_number_last_digits
        new_payments[0]['card_expiry_date'] = debit_card_details.card_expiry_date
        new_payments[0]['recipient_name'] = 'Mr. John Doe'

        new_payments[0]['prisoner_number'] = prisoner_profile.prisoner_number
        new_payments[0]['prisoner_dob'] = prisoner_profile.prisoner_dob

        create_payments(new_payments)
        call_command('update_security_profiles', verbosity=0)

        prisoner_profile.refresh_from_db()
        recipient_names = list(recipient_name.name for recipient_name in prisoner_profile.provided_names.all())
        self.assertEqual(recipient_names[-1], 'Mr. John Doe')


class UpdateCurrentPrisonsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()

    def test_update_current_prisons(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles', verbosity=0)

        def check_locations():
            for prisoner_profile in PrisonerProfile.objects.all():
                current_location = PrisonerLocation.objects.get(
                    prisoner_number=prisoner_profile.prisoner_number,
                    active=True
                )
                self.assertEqual(prisoner_profile.current_prison, current_location.prison)

        check_locations()

        for location in PrisonerLocation.objects.all():
            location.prison = Prison.objects.all().order_by('?').first()

        call_command('update_current_prisons')
        check_locations()
