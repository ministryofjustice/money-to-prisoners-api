import datetime
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.test.utils import captured_stdout
from django.utils import timezone

from credit.models import Credit, Log as CreditLog
from disbursement.models import Disbursement, Log as DisbursementLog
from notification.tests.utils import make_recipient
from notification.models import Event, CreditEvent, DisbursementEvent, PrisonerProfileEvent, RecipientProfileEvent, SenderProfileEvent
from payment.models import Payment
from security.models import  PrisonerProfile, RecipientProfile, SenderProfile, BankTransferRecipientDetails, BankAccount
from transaction.models import Transaction


class TestDeleteOldData(TestCase):
    """
    ```mermaid
    mindmap
        root
            SenderProfile1_UPDATED
                Credit1_DELETED
                Credit2
                Credit3
            SenderProfile2_DELETED
                Credit4_DELETED
            PrisonerProfile1_UPDATED
                Credit1_DELETED
                Credit2
                Credit3
                Disbursement1_DELETED
                Disbursement3_DELETED
                Disbursement4_DELETED
            PrisonerProfile2_DELETED
                Credit4_DELETED
                Disbursement2_DELETED
            RecipientProfile1_DELETED
                Disbursement1_DELETED
            RecipientProfile2_DELETED
                Disbursement2_DELETED
            RecipientProfile3_UPDATED
                Disbursement3_DELETED
                Disbursement4
    ```
    """
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json', 'test_delete_old_data.json']

    def setUp(self):
        super().setUp()
        self.today = datetime.date(2023, 1, 1)

        self.sender_profile_1_update = SenderProfile.objects.get(pk=1)
        self.sender_profile_event_1 = SenderProfileEvent.objects.get(pk=1)
        # NOTE: Event are shared between various records so PK may not match
        self.event_9 = self.sender_profile_event_1.event
        self.sender_profile_2_delete = SenderProfile.objects.get(pk=2)
        self.sender_profile_event_2_delete = SenderProfileEvent.objects.get(pk=2)
        # NOTE: Event are shared between various records so PK may not match
        self.event_10_delete = self.sender_profile_event_2_delete.event

        self.prisoner_profile_1_update = PrisonerProfile.objects.get(pk=1)
        self.prisoner_profile_event_1 = PrisonerProfileEvent.objects.get(pk=1)
        # NOTE: Event are shared between various records so PK may not match
        self.event_13 = self.prisoner_profile_event_1.event
        self.prisoner_profile_2_delete = PrisonerProfile.objects.get(pk=2)
        self.prisoner_profile_event_2_delete = PrisonerProfileEvent.objects.get(pk=2)
        # NOTE: Event are shared between various records so PK may not match
        self.event_14_delete = self.prisoner_profile_event_2_delete.event

        self.recipient_profile_1_delete = RecipientProfile.objects.get(pk=1)
        self.recipient_profile_event_1_delete = RecipientProfileEvent.objects.get(pk=1)
        # NOTE: Event are shared between various records so PK may not match
        self.event_15_delete = self.recipient_profile_event_1_delete.event
        self.recipient_profile_2_delete = RecipientProfile.objects.get(pk=2)
        self.recipient_profile_event_2_delete = RecipientProfileEvent.objects.get(pk=2)
        # NOTE: Event are shared between various records so PK may not match
        self.event_11_delete = self.recipient_profile_event_2_delete.event
        self.recipient_profile_3_update = RecipientProfile.objects.get(pk=3)
        self.recipient_profile_event_3 = RecipientProfileEvent.objects.get(pk=3)
        # NOTE: Event are shared between various records so PK may not match
        self.event_12 = self.recipient_profile_event_3.event

        self.credit_1_delete = Credit.objects.get(pk=1)
        self.payment_1_delete = Payment.objects.get(pk=1)
        self.credit_log_1_delete = CreditLog.objects.get(pk=1)
        self.credit_event_1_delete = CreditEvent.objects.get(pk=1)
        self.event_1_delete = self.credit_event_1_delete.event

        self.credit_2 = Credit.objects.get(pk=2)
        self.payment_2 = Payment.objects.get(pk=2)
        self.credit_log_2 = CreditLog.objects.get(pk=2)
        self.credit_event_2 = CreditEvent.objects.get(pk=2)
        # NOTE: Event are shared between various records so PK may not match
        self.event_3 = self.credit_event_2.event

        self.credit_3 = Credit.objects.get(pk=3)
        self.payment_3 = Payment.objects.get(pk=3)
        self.credit_log_3 = CreditLog.objects.get(pk=3)
        self.credit_event_3 = CreditEvent.objects.get(pk=3)
        # NOTE: Event are shared between various records so PK may not match
        self.event_4 = self.credit_event_3.event

        self.credit_4_delete = Credit.objects.get(pk=4)
        self.payment_4_delete = Payment.objects.get(pk=4)
        self.credit_log_4_delete = CreditLog.objects.get(pk=4)
        self.credit_event_4_delete = CreditEvent.objects.get(pk=4)
        # NOTE: Event are shared between various records so PK may not match
        self.event_5_delete = self.credit_event_4_delete.event

        self.disbursement_1_delete = Disbursement.objects.get(pk=1)
        self.bank_transfer_recipient_details_1_delete = BankTransferRecipientDetails.objects.get(pk=1)
        self.bank_account_1_delete = self.bank_transfer_recipient_details_1_delete.recipient_bank_account
        self.disbursement_log_1_delete = DisbursementLog.objects.get(pk=1)
        self.disbursement_event_1_delete = DisbursementEvent.objects.get(pk=1)
        # NOTE: Event are shared between various records so PK may not match
        self.event_2_delete = self.disbursement_event_1_delete.event

        self.disbursement_2_delete = Disbursement.objects.get(pk=2)
        self.bank_transfer_recipient_details_2_delete = BankTransferRecipientDetails.objects.get(pk=1)
        self.bank_account_2_delete = self.bank_transfer_recipient_details_2_delete.recipient_bank_account
        self.disbursement_log_2_delete = DisbursementLog.objects.get(pk=2)
        self.disbursement_event_2_delete = DisbursementEvent.objects.get(pk=2)
        # NOTE: Event are shared between various records so PK may not match
        self.event_6_delete = self.disbursement_event_2_delete.event

        self.disbursement_3_delete = Disbursement.objects.get(pk=3)
        self.disbursement_log_3_delete = DisbursementLog.objects.get(pk=3)
        self.disbursement_event_3_delete = DisbursementEvent.objects.get(pk=3)
        # NOTE: Event are shared between various records so PK may not match
        self.event_7_delete = self.disbursement_event_2_delete.event

        self.disbursement_4 = Disbursement.objects.get(pk=4)
        # NOTE: Disbursement 3 also sent to BankAccount 3/RecipientProfile 3
        self.bank_transfer_recipient_details_3 = BankTransferRecipientDetails.objects.get(pk=3)
        self.bank_account_3 = self.bank_transfer_recipient_details_3.recipient_bank_account
        self.disbursement_log_4 = DisbursementLog.objects.get(pk=4)
        self.disbursement_event_4 = DisbursementEvent.objects.get(pk=4)
        # NOTE: Event are shared between various records so PK may not match
        self.event_8_delete = self.disbursement_event_2_delete.event

        self.transaction_1_delete = Transaction.objects.get(pk=1)
        self.transaction_2 = Transaction.objects.get(pk=2)

    @mock.patch('django.utils.timezone.localdate')
    def test_deletes_old_data(self, mocked_localdate):
        mocked_localdate.return_value = self.today

        with captured_stdout() as stdout:
            call_command('delete_old_data')

        stdout = stdout.getvalue()
        print(f"OUTPUT = ~~~~~~~~~~~~\n{stdout}~~~~~~~~~~~~\n")

        # Credit 1 deleted (and related records)
        self.assertRaises(Credit.DoesNotExist, self.credit_1_delete.refresh_from_db)
        self.assertRaises(Payment.DoesNotExist, self.payment_1_delete.refresh_from_db)
        self.assertRaises(CreditLog.DoesNotExist, self.credit_log_1_delete.refresh_from_db)
        self.assertRaises(CreditEvent.DoesNotExist, self.credit_event_1_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_1_delete.refresh_from_db)
        self.assertIn("Deleting Credit Credit 1, £10 Mrs. Halls > JAMES HALLS, credited...", stdout)

        # Credit 2 and related records untouched
        self.credit_2.refresh_from_db()
        self.payment_2.refresh_from_db()

        # Credit 3 and related records untouched
        self.credit_3.refresh_from_db()
        self.payment_3.refresh_from_db()

        # Credit 4 deleted (and related records)
        self.assertRaises(Credit.DoesNotExist, self.credit_4_delete.refresh_from_db)
        self.assertRaises(Payment.DoesNotExist, self.payment_4_delete.refresh_from_db)
        self.assertRaises(CreditLog.DoesNotExist, self.credit_log_4_delete.refresh_from_db)
        self.assertRaises(CreditEvent.DoesNotExist, self.credit_event_4_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_5_delete.refresh_from_db)
        self.assertIn("Deleting Credit Credit 4, £40 Mrs. Walls > JOHN WALLS, credited...", stdout)

        # Disbursement 1 deleted (and related records)
        self.assertRaises(Disbursement.DoesNotExist, self.disbursement_1_delete.refresh_from_db)
        self.assertRaises(BankTransferRecipientDetails.DoesNotExist, self.bank_transfer_recipient_details_1_delete.refresh_from_db)
        self.assertRaises(BankAccount.DoesNotExist, self.bank_account_1_delete.refresh_from_db)
        self.assertRaises(DisbursementLog.DoesNotExist, self.disbursement_log_1_delete.refresh_from_db)
        self.assertRaises(DisbursementEvent.DoesNotExist, self.disbursement_event_1_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_2_delete.refresh_from_db)
        self.assertIn("Deleting Disbursement Disbursement 1, £10 A1409AE > , sent...", stdout)

        # Disbursement 2 deleted (and related records)
        self.assertRaises(Disbursement.DoesNotExist, self.disbursement_2_delete.refresh_from_db)
        self.assertRaises(BankTransferRecipientDetails.DoesNotExist, self.bank_transfer_recipient_details_2_delete.refresh_from_db)
        self.assertRaises(BankAccount.DoesNotExist, self.bank_account_2_delete.refresh_from_db)
        self.assertRaises(DisbursementLog.DoesNotExist, self.disbursement_log_2_delete.refresh_from_db)
        self.assertRaises(DisbursementEvent.DoesNotExist, self.disbursement_event_2_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_6_delete.refresh_from_db)
        self.assertIn("Deleting Disbursement Disbursement 2, £20 B1510BF > , sent...", stdout)

        # Disbursement 3 deleted (and related records)
        self.assertRaises(Disbursement.DoesNotExist, self.disbursement_3_delete.refresh_from_db)
        self.assertRaises(DisbursementLog.DoesNotExist, self.disbursement_log_3_delete.refresh_from_db)
        self.assertRaises(DisbursementEvent.DoesNotExist, self.disbursement_event_3_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_7_delete.refresh_from_db)
        self.assertIn("Deleting Disbursement Disbursement 3, £30 A1409AE > , sent...", stdout)

        # Disbursement 4 untouched
        self.disbursement_4.refresh_from_db()
        # NOTE: Disbursement 4 also sent to RecipientProfile 3
        self.bank_transfer_recipient_details_3.refresh_from_db()
        self.bank_account_3.refresh_from_db()

        # Transaction 1 deleted
        self.assertRaises(Transaction.DoesNotExist, self.transaction_1_delete.refresh_from_db)

        # Transaction 2 untouched
        self.transaction_2.refresh_from_db()

        # Sender Profile 1 updated (Credit 1 was deleted)
        self.sender_profile_1_update.refresh_from_db()
        self.assertEqual(self.sender_profile_1_update.credit_count, 1)
        self.assertEqual(self.sender_profile_1_update.credit_total, self.credit_2.amount)
        self.assertEqual([c.id for c in self.sender_profile_1_update.credits.all()], [self.credit_2.id, self.credit_3.id])
        self.assertIn("SenderProfile Sender 1 updated.", stdout)
        # Event/SenderProfileEvent records not deleted
        self.sender_profile_event_1.refresh_from_db()
        self.event_9.refresh_from_db()

        # Sender Profile 2 deleted (Credit 4 was deleted and was only credit)
        self.assertRaises(SenderProfile.DoesNotExist, self.sender_profile_2_delete.refresh_from_db)
        self.assertIn("SenderProfile Sender 2 has no credits, deleting...", stdout)
        # Event/SenderProfileEvent records deleted
        self.assertRaises(SenderProfileEvent.DoesNotExist, self.sender_profile_event_2_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_10_delete.refresh_from_db)

        # Prisoner Profile 1 updated (Credit 1 was deleted/Disbursements 1/3 deleted)
        self.prisoner_profile_1_update.refresh_from_db()
        self.assertEqual(self.prisoner_profile_1_update.credit_count, 1)
        self.assertEqual(self.prisoner_profile_1_update.credit_total, self.credit_2.amount)
        self.assertEqual(self.prisoner_profile_1_update.disbursement_count, 1)
        self.assertEqual(self.prisoner_profile_1_update.disbursement_total, self.disbursement_4.amount)
        self.assertIn("PrisonerProfile Prisoner 1 (A1409AE) updated.", stdout)
        # Event/PrisonerProfileEvent records not deleted
        self.prisoner_profile_event_1.refresh_from_db()
        self.event_13.refresh_from_db()

        # Prisoner Profile 2 deleted (Credit 4 and Disbursement 2 deleted, nothing left)
        self.assertRaises(PrisonerProfile.DoesNotExist, self.prisoner_profile_2_delete.refresh_from_db)
        self.assertIn("PrisonerProfile Prisoner 2 (B1510BF) has no credits nor disbursements, deleting...", stdout)
        # Event/PrisonerProfileEvent records deleted
        self.assertRaises(PrisonerProfileEvent.DoesNotExist, self.prisoner_profile_event_2_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_14_delete.refresh_from_db)

        # Recipient Profile 1 deleted (Disbursement 1 was deleted and was the only disbursement)
        self.assertRaises(RecipientProfile.DoesNotExist, self.recipient_profile_1_delete.refresh_from_db)
        self.assertIn("RecipientProfile Recipient 1 has no disbursements, deleting...", stdout)
        # Event/RecipientProfileEvent records deleted
        self.assertRaises(RecipientProfileEvent.DoesNotExist, self.recipient_profile_event_1_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_15_delete.refresh_from_db)

        # Recipient Profile 2 deleted (Disbursement 2 was deleted and was the only disbursement)
        self.assertRaises(RecipientProfile.DoesNotExist, self.recipient_profile_1_delete.refresh_from_db)
        self.assertIn("RecipientProfile Recipient 2 has no disbursements, deleting...", stdout)
        # Event/RecipientProfileEvent records deleted
        self.assertRaises(RecipientProfileEvent.DoesNotExist, self.recipient_profile_event_2_delete.refresh_from_db)
        self.assertRaises(Event.DoesNotExist, self.event_11_delete.refresh_from_db)

        # Recipient Profile 3 updated (Disbursement 3 was deleted)
        self.recipient_profile_3_update.refresh_from_db()
        self.assertEqual(self.recipient_profile_3_update.disbursement_count, 1)
        self.assertEqual(self.recipient_profile_3_update.disbursement_total, self.disbursement_4.amount)
        self.assertIn("RecipientProfile Recipient 3 updated.", stdout)
        # Event/RecipientProfileEvent records not deleted
        self.recipient_profile_event_3.refresh_from_db()
        self.event_12.refresh_from_db()

        seven_years_ago = self.today - datetime.timedelta(days=7*365)
        self.assertIn(f'older than {seven_years_ago}', stdout)
        self.assertIn("Records deleted: (3, {'payment.Payment': 1, 'credit.Log': 1, 'credit.Credit': 1}).", stdout)
        self.assertIn("Records deleted: (2, {'notification.CreditEvent': 1, 'notification.Event': 1}).", stdout)
        self.assertIn("Records deleted: (2, {'disbursement.Log': 1, 'disbursement.Disbursement': 1}).", stdout)
        self.assertIn("Records deleted: (2, {'notification.DisbursementEvent': 1, 'notification.Event': 1}).", stdout)
        self.assertIn("Records deleted: (1, {'transaction.Transaction': 1}).", stdout)
