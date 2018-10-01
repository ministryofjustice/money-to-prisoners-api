from django.core.management import call_command
from django.test import TestCase

from core.tests.utils import make_test_users
from credit.models import Credit
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import SenderProfile, BankTransferSenderDetails, DebitCardSenderDetails
from transaction.tests.utils import generate_transactions


class SenderProfileTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        call_command('update_security_profiles')

    def test_credit_filters(self):
        sender = SenderProfile.objects.filter(bank_transfer_details__isnull=False).first()
        bank_details = sender.bank_transfer_details.first()

        credits = Credit.objects.filter(
            transaction__sender_name=bank_details.sender_name,
            transaction__sender_sort_code=bank_details.sender_bank_account.sort_code,
            transaction__sender_account_number=bank_details.sender_bank_account.account_number,
            transaction__sender_roll_number=bank_details.sender_bank_account.roll_number
        ).order_by('id')

        filtered_credits = Credit.objects.filter(
            sender.credit_filters
        ).order_by('id')

        self.assertEqual(list(credits), list(filtered_credits))

    def test_credit_filters_on_empty_profile(self):
        credits = Credit.objects.none()
        filtered_credits = Credit.objects.filter(
            SenderProfile().credit_filters
        ).order_by('id')

        self.assertEqual(list(credits), list(filtered_credits))

    def test_credit_filters_on_multiple_details(self):
        sender = SenderProfile.objects.filter(bank_transfer_details__isnull=False).first()
        bank_details = sender.bank_transfer_details.first()

        extra_bank_details = BankTransferSenderDetails.objects.exclude(sender=sender).first()
        debit_card_details = DebitCardSenderDetails.objects.first()

        extra_bank_details.sender = sender
        extra_bank_details.save()

        debit_card_details.sender = sender
        debit_card_details.save()

        sender.refresh_from_db()

        credits_1 = Credit.objects.filter(
            transaction__sender_name=bank_details.sender_name,
            transaction__sender_sort_code=bank_details.sender_bank_account.sort_code,
            transaction__sender_account_number=bank_details.sender_bank_account.account_number,
            transaction__sender_roll_number=bank_details.sender_bank_account.roll_number
        )

        credits_2 = Credit.objects.filter(
            transaction__sender_name=extra_bank_details.sender_name,
            transaction__sender_sort_code=extra_bank_details.sender_bank_account.sort_code,
            transaction__sender_account_number=extra_bank_details.sender_bank_account.account_number,
            transaction__sender_roll_number=extra_bank_details.sender_bank_account.roll_number
        )

        credits_3 = Credit.objects.filter(
            payment__card_number_last_digits=debit_card_details.card_number_last_digits,
            payment__card_expiry_date=debit_card_details.card_expiry_date,
        )

        filtered_credits = Credit.objects.filter(
            sender.credit_filters
        )

        self.assertEqual(
            filtered_credits.count(),
            credits_1.count() + credits_2.count() + credits_3.count()
        )
        for credit in filtered_credits:
            self.assertTrue(
                credits_1.filter(id=credit.id).exists() or
                credits_2.filter(id=credit.id).exists() or
                credits_3.filter(id=credit.id).exists()
            )
