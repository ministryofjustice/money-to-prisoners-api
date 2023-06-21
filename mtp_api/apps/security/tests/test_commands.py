from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.test.utils import captured_stdout
from faker import Faker
from model_bakery import baker

from mtp_common.test_utils import silence_logger

from credit.constants import CreditResolution
from credit.models import Credit
from core.tests.utils import make_test_users, delete_non_related_nullable_fields
from disbursement.constants import DisbursementResolution, DisbursementMethod
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements, generate_initial_disbursement_data, create_disbursements

from payment.models import Payment
from payment.tests.utils import create_payments, generate_payments, generate_initial_payment_data
from prison.models import PrisonerLocation, Prison
from prison.tests.utils import load_random_prisoner_locations
from security.models import (
    SenderProfile, PrisonerProfile, RecipientProfile,
    BankAccount, BankTransferSenderDetails, DebitCardSenderDetails,
    SavedSearch, SearchFilter,
)
from transaction.tests.utils import create_transactions, generate_initial_transactions_data, generate_transactions
from transaction.models import Transaction


class UpdateSecurityProfilesTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users()
        load_random_prisoner_locations()

    def _assert_counts(self):
        for sender_profile in SenderProfile.objects.all():
            self.assertEqual(
                sender_profile.credits.filter(
                    resolution=CreditResolution.credited,
                ).count(),
                sender_profile.credit_count
            )
            self.assertEqual(
                sum(credit.amount for credit in sender_profile.credits.filter(
                    resolution=CreditResolution.credited,
                )),
                sender_profile.credit_total
            )

        self.assertEqual(
            Credit.objects.filter(
                is_counted_in_sender_profile_total=False,
                resolution=CreditResolution.credited,
            ).count(),
            0
        )

        for recipient_profile in RecipientProfile.objects.filter(
            bank_transfer_details__isnull=False
        ):
            self.assertEqual(
                sum(disbursement.amount for disbursement in recipient_profile.disbursements.all()),
                recipient_profile.disbursement_total
            )
            self.assertEqual(
                recipient_profile.disbursements.all().count(),
                recipient_profile.disbursement_count
            )

        for prisoner_profile in PrisonerProfile.objects.all():
            self.assertEqual(
                sum(credit.amount for credit in prisoner_profile.credits.filter(
                    resolution=CreditResolution.credited,
                )),
                prisoner_profile.credit_total
            )
            self.assertEqual(
                prisoner_profile.credits.filter(
                    resolution=CreditResolution.credited,
                ).count(),
                prisoner_profile.credit_count
            )

            self.assertEqual(
                sum(disbursement.amount for disbursement in prisoner_profile.disbursements.all()),
                prisoner_profile.disbursement_total
            )
            self.assertEqual(
                prisoner_profile.disbursements.all().count(),
                prisoner_profile.disbursement_count
            )
        self.assertEqual(
            Credit.objects.filter(
                is_counted_in_prisoner_profile_total=False,
                resolution=CreditResolution.credited,
            ).count(),
            0
        )

    @captured_stdout()
    @silence_logger()
    def test_update_security_profiles_initial(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        call_command('update_security_profiles', verbosity=0)
        self._assert_counts()

    @captured_stdout()
    @silence_logger()
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
        new_transactions[0]['sender_sort_code'] = bank_details.sender_bank_account.sort_code
        new_transactions[0]['sender_account_number'] = bank_details.sender_bank_account.account_number
        new_transactions[0]['sender_roll_number'] = bank_details.sender_bank_account.roll_number

        new_transactions[0]['prisoner_number'] = prisoner_to_update.prisoner_number
        new_transactions[0]['prisoner_dob'] = prisoner_to_update.prisoner_dob

        create_transactions(new_transactions, overrides={'credited': True})
        call_command('update_security_profiles', verbosity=0)

        sender_to_update.refresh_from_db()
        self.assertEqual(
            sender_to_update.credit_count,
            initial_sender_credit_count + 1
        )
        self.assertEqual(
            sender_to_update.credit_total,
            initial_sender_credit_total + new_transactions[0]['amount']
        )

        prisoner_to_update.refresh_from_db()
        self.assertEqual(
            prisoner_to_update.credit_count,
            initial_prisoner_credit_count + 1
        )
        self.assertEqual(
            prisoner_to_update.credit_total,
            initial_prisoner_credit_total + new_transactions[0]['amount']
        )

    @captured_stdout()
    @silence_logger()
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

        initial_sender_credit_count = sender_to_update.credit_count
        initial_sender_credit_total = sender_to_update.credit_total
        initial_sender_cardholder_names = list(card_details.cardholder_names.values_list('name', flat=True))
        initial_sender_emails = list(card_details.sender_emails.values_list('email', flat=True))
        initial_prisoner_credit_count = prisoner_to_update.credit_count
        initial_prisoner_credit_total = prisoner_to_update.credit_total

        new_payments = generate_initial_payment_data(tot=1, days_of_history=0)

        new_payments[0]['created'] = timezone.now()

        new_payments[0]['email'] = 'dude@mtp.local'
        new_payments[0]['cardholder_name'] = 'other name'
        new_payments[0]['card_number_last_digits'] = card_details.card_number_last_digits
        new_payments[0]['card_expiry_date'] = card_details.card_expiry_date
        new_payments[0]['billing_address']['postcode'] = card_details.postcode

        new_payments[0]['prisoner_number'] = prisoner_to_update.prisoner_number
        new_payments[0]['prisoner_dob'] = prisoner_to_update.prisoner_dob

        create_payments(new_payments, overrides={'credited': True})
        call_command('update_security_profiles', verbosity=0)

        sender_to_update.refresh_from_db()
        self.assertEqual(
            sender_to_update.credit_count,
            initial_sender_credit_count + 1
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
            prisoner_to_update.credit_count,
            initial_prisoner_credit_count + 1
        )
        self.assertEqual(
            prisoner_to_update.credit_total,
            initial_prisoner_credit_total + new_payments[0]['amount']
        )

    @captured_stdout()
    @silence_logger()
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

        initial_recipient_disbursement_count = recipient_to_update.disbursement_count
        initial_recipient_disbursement_total = recipient_to_update.disbursement_total
        initial_prisoner_disbursement_count = prisoner_to_update.disbursement_count
        initial_prisoner_disbursement_total = prisoner_to_update.disbursement_total

        new_disbursements = generate_initial_disbursement_data(
            tot=1, days_of_history=0
        )

        new_disbursements[0]['method'] = DisbursementMethod.bank_transfer.value
        new_disbursements[0]['sort_code'] = bank_details.recipient_bank_account.sort_code
        new_disbursements[0]['account_number'] = bank_details.recipient_bank_account.account_number
        new_disbursements[0]['roll_number'] = bank_details.recipient_bank_account.roll_number

        new_disbursements[0]['prisoner_number'] = prisoner_to_update.prisoner_number
        new_disbursements[0]['prisoner_name'] = prisoner_to_update.prisoner_name
        new_disbursements[0]['resolution'] = DisbursementResolution.sent.value

        create_disbursements(new_disbursements)
        call_command('update_security_profiles', verbosity=0)

        recipient_to_update.refresh_from_db()
        self.assertEqual(
            recipient_to_update.disbursement_count,
            initial_recipient_disbursement_count + 1
        )
        self.assertEqual(
            recipient_to_update.disbursement_total,
            initial_recipient_disbursement_total + new_disbursements[0]['amount']
        )

        prisoner_to_update.refresh_from_db()
        self.assertEqual(
            prisoner_to_update.disbursement_count,
            initial_prisoner_disbursement_count + 1
        )
        self.assertEqual(
            prisoner_to_update.disbursement_total,
            initial_prisoner_disbursement_total + new_disbursements[0]['amount']
        )

    @captured_stdout()
    @silence_logger()
    def test_update_prisoner_profiles(self):
        payments = generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles', verbosity=0)

        valid_payments = filter(lambda payment: payment.credit.prison, payments)
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
        self._assert_counts()

    @captured_stdout()
    @silence_logger()
    def test_profile_update_minimum_viable_data(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)

        delete_non_related_nullable_fields(
            Payment.objects.all(),
            null_fields_to_leave_populated={
                'email',
                'cardholder_name',
                'card_number_first_digits',
                'card_number_last_digits',
                'card_expiry_date',
                'billing_address',
            }
        )
        delete_non_related_nullable_fields(
            Transaction.objects.all(),
            null_fields_to_leave_populated={
                'sender_name',
                'sender_sort_code',
                'sender_account_number'
            }
        )
        delete_non_related_nullable_fields(
            Credit.objects.all(),
            null_fields_to_leave_populated={
                'prison',
                'prisoner_name',
                'prisoner_number',  # Needed to populate PrisonerProfile
            }
        )
        delete_non_related_nullable_fields(
            Disbursement.objects.all(),
            null_fields_to_leave_populated={
                'sort_code',  # Needed to populate BankAccount
                'account_number'  # Needed to populate BankAccount
            }
        )

        call_command('update_security_profiles', verbosity=0)

        self._assert_counts()


class UpdateCurrentPrisonsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users()
        load_random_prisoner_locations()

    @captured_stdout()
    @silence_logger()
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


class BulkUnmonitorCommandTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=0, num_security_fiu_users=1)
        self.security_staff = test_users['security_staff']

    @captured_stdout()
    def test_bulk_unmonitor(self):
        fake = Faker(locale='en_GB')
        for user in self.security_staff:
            baker.make(
                BankTransferSenderDetails,
                sender=baker.make(SenderProfile),
                sender_bank_account=baker.make(
                    BankAccount,
                    sort_code=get_random_string(6, '0123456789'),
                    account_number=get_random_string(8, '0123456789'),
                    monitoring_users=[user],
                ),
            )
            baker.make(
                DebitCardSenderDetails,
                sender=baker.make(SenderProfile),
                card_number_last_digits=fake.credit_card_number()[-4:],
                card_expiry_date=fake.credit_card_expire(),
                postcode=fake.postcode(),
                monitoring_users=[user],
            )
            baker.make(PrisonerProfile, monitoring_users=[user])
            for _ in range(3):
                baker.make(SearchFilter, saved_search=baker.make(SavedSearch, user=user))

        bank_account_count = BankAccount.objects.count()
        debit_card_sender_count = DebitCardSenderDetails.objects.count()
        prisoner_profile_count = PrisonerProfile.objects.count()

        chosen_user, other_users = self.security_staff[0], self.security_staff[1:]
        # ensure chosen user actually monitored 1 of each model
        self.assertEqual(BankAccount.objects.filter(monitoring_users=chosen_user).count(), 1)
        self.assertEqual(DebitCardSenderDetails.objects.filter(monitoring_users=chosen_user).count(), 1)
        self.assertEqual(PrisonerProfile.objects.filter(monitoring_users=chosen_user).count(), 1)
        # ensure that chosen user had 3 saved searches
        self.assertEqual(SavedSearch.objects.filter(user=chosen_user).count(), 3)
        call_command('bulk_unmonitor', chosen_user.username)
        # assert that chosen user no longer monitors anything
        self.assertEqual(BankAccount.objects.filter(monitoring_users=chosen_user).count(), 0)
        self.assertEqual(DebitCardSenderDetails.objects.filter(monitoring_users=chosen_user).count(), 0)
        self.assertEqual(PrisonerProfile.objects.filter(monitoring_users=chosen_user).count(), 0)
        # assert that chosen user has no saved searches
        self.assertEqual(SavedSearch.objects.filter(user=chosen_user).count(), 0)
        # assert that security profiles are not deleted (only unmonitored)
        self.assertEqual(BankAccount.objects.count(), bank_account_count)
        self.assertEqual(DebitCardSenderDetails.objects.count(), debit_card_sender_count)
        self.assertEqual(PrisonerProfile.objects.count(), prisoner_profile_count)
        # assert that other users still monitor each model and have saved searcges
        for user in other_users:
            self.assertEqual(BankAccount.objects.filter(monitoring_users=user).count(), 1)
            self.assertEqual(DebitCardSenderDetails.objects.filter(monitoring_users=user).count(), 1)
            self.assertEqual(PrisonerProfile.objects.filter(monitoring_users=user).count(), 1)
            self.assertEqual(SavedSearch.objects.filter(user=user).count(), 3)
