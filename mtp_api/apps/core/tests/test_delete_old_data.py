import datetime
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.test.utils import captured_stdout
from django.utils import timezone
from model_bakery import baker

from credit.models import Credit, CreditResolution
from disbursement.models import Disbursement, DisbursementResolution
from notification.tests.utils import make_recipient
from payment.models import Payment, PaymentStatus
from security.models import RecipientProfile
from transaction.models import Transaction, TransactionSource


class TestDeleteOldData(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.today = datetime.date(2023, 1, 1)
        old_datetime = timezone.make_aware(datetime.datetime(2015, 11, 11, 9))
        new_datetime = timezone.make_aware(datetime.datetime(2022, 12, 31, 9))

        self.old_credit: Credit = baker.make(
            Credit,
            prisoner_number='A1409AE',
            prisoner_name='JAMES HALLS',
            prison_id='IXB',
            amount=3000,
            created=old_datetime,
            received_at=old_datetime,
            resolution=CreditResolution.pending.value,
        )
        self.old_payment = baker.make(
            Payment,
            credit=self.old_credit,
            amount=self.old_credit.amount,
            status=PaymentStatus.taken,
            cardholder_name='Mrs. Halls',
            created=old_datetime,
            modified=old_datetime,
        )
        self.recipient = make_recipient()
        self.old_disbursement = baker.make(
            Disbursement,
            amount=4000,
            recipient_profile=self.recipient,
            created=old_datetime,
            resolution=DisbursementResolution.sent,
        )
        self.old_transaction = baker.make(
            Transaction,
            source=TransactionSource.bank_transfer,
            received_at=old_datetime,
        )

        self.new_credit: Credit = baker.make(
            Credit,
            prisoner_number='A1409AE',
            prisoner_name='JAMES HALLS',
            prison_id='IXB',
            amount=3000,
            created=new_datetime,
            received_at=new_datetime,
            resolution=CreditResolution.pending.value,
        )
        self.new_payment = baker.make(
            Payment,
            credit=self.new_credit,
            amount=self.new_credit.amount,
            status=PaymentStatus.taken,
            cardholder_name='Mrs. Halls',
            created=new_datetime,
            modified=new_datetime,
        )
        self.new_disbursement = baker.make(
            Disbursement,
            amount=5000,
            recipient_profile=self.recipient,
            created=new_datetime,
            resolution=DisbursementResolution.sent,
        )
        self.new_transaction = baker.make(
            Transaction,
            source=TransactionSource.administrative,
            received_at=new_datetime,
        )

    @mock.patch('django.utils.timezone.localdate')
    def test_deletes_old_data(self, mocked_localdate):
        mocked_localdate.return_value = self.today

        credits = [(credit.id, credit.prisoner_name, credit.created) for credit in Credit.objects.all()]
        disbursements = [(disbursement.id, disbursement.created) for disbursement in Disbursement.objects.all()]
        transactions = [(tx.id, tx.received_at) for tx in Transaction.objects.all()]
        print(f'CREDITS BEFORE = {credits}')
        print(f'DISBURSEMENTES BEFORE = {disbursements}')
        print(f'TRANSACTIONS BEFORE = {transactions}')

        with captured_stdout() as stdout:
            call_command('delete_old_data')

        credits = [(credit.id, credit.prisoner_name, credit.created) for credit in Credit.objects.all()]
        disbursements = [(disbursement.id, disbursement.created) for disbursement in Disbursement.objects.all()]
        transactions = [(tx.id, tx.received_at) for tx in Transaction.objects.all()]
        print(f'CREDITS AFTER = {credits}')
        print(f'DISBURSEMENTES AFTER = {disbursements}')
        print(f'TRANSACTIONS AFTER = {transactions}')

        # Deletes records older than 7 years
        self.assertFalse(Credit.objects.filter(id=self.old_credit.pk).exists())
        self.assertFalse(Payment.objects.filter(uuid=self.old_payment.pk).exists())
        self.assertFalse(Disbursement.objects.filter(id=self.old_disbursement.pk).exists())
        self.assertFalse(Transaction.objects.filter(id=self.old_transaction.pk).exists())

        # Does NOT delete records from the last 7 years
        self.assertTrue(Credit.objects.filter(id=self.new_credit.pk).exists())
        self.assertTrue(Payment.objects.filter(uuid=self.new_payment.pk).exists())
        self.assertTrue(Disbursement.objects.filter(id=self.new_disbursement.pk).exists())
        # Recipient not deleted even if the related old disbursement was deleted
        self.assertTrue(RecipientProfile.objects.filter(id=self.recipient.pk).exists())
        self.assertTrue(Transaction.objects.filter(id=self.new_transaction.pk).exists())

        stdout = stdout.getvalue()
        print(stdout)

        seven_years_ago = self.today - datetime.timedelta(days=7*365)
        self.assertIn(f'older than {seven_years_ago}', stdout)
        self.assertIn('Records deleted: (2, {\'payment.Payment\': 1, \'credit.Credit\': 1})', stdout)
        self.assertIn('Records deleted: (1, {\'disbursement.Disbursement\': 1})', stdout)
        self.assertIn('Records deleted: (1, {\'transaction.Transaction\': 1})', stdout)
