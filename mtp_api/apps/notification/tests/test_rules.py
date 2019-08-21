import datetime
import random

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django.utils.crypto import get_random_string
from faker import Faker
from model_mommy import mommy

from core.tests.utils import make_test_users
from credit.models import Credit, CREDIT_RESOLUTION
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from notification.models import (
    SenderProfileEvent, RecipientProfileEvent, PrisonerProfileEvent
)
from notification.rules import Event, RULES
from payment.models import Payment
from payment.tests.utils import generate_payments
from prison.models import Prison
from prison.tests.utils import (
    load_random_prisoner_locations, random_prisoner_name, random_prisoner_number, random_prisoner_dob,
)
from security.models import (
    SenderProfile, RecipientProfile, PrisonerProfile,
    DebitCardSenderDetails, BankAccount, BankTransferRecipientDetails,
)
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions

fake = Faker(locale='en_GB')


class RuleTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.user = test_users['security_staff'][0]
        load_random_prisoner_locations()
        # generate random data which may or may not match amount rules
        generate_transactions(transaction_batch=200, days_of_history=3)
        generate_payments(payment_batch=200, days_of_history=3)
        generate_disbursements(disbursement_batch=200, days_of_history=3)

        # £1 does not match NWN or HA rules and no monitoring exists, i.e. no non-counting rules can trigger
        Payment.objects.update(amount=100)
        Transaction.objects.update(amount=100)
        Credit.objects.update(amount=100)
        Disbursement.objects.update(amount=100)

    def assertEventMatchesRecord(self, events, record, profile_class=None):  # noqa: N802
        for event in events:
            if isinstance(record, Credit):
                self.assertEqual(event.credit_event.credit, record)
            if isinstance(record, Disbursement):
                self.assertEqual(event.disbursement_event.disbursement, record)

            if profile_class == SenderProfile:
                self.assertEqual(
                    event.sender_profile_event.sender_profile,
                    record.sender_profile
                )
            else:
                with self.assertRaises(SenderProfileEvent.DoesNotExist):
                    print(event.sender_profile_event)

            if profile_class == RecipientProfile:
                self.assertEqual(
                    event.recipient_profile_event.recipient_profile,
                    record.recipient_profile
                )
            else:
                with self.assertRaises(RecipientProfileEvent.DoesNotExist):
                    print(event.recipient_profile_event)

            if profile_class == PrisonerProfile:
                self.assertEqual(
                    event.prisoner_profile_event.prisoner_profile,
                    record.prisoner_profile
                )
            else:
                with self.assertRaises(PrisonerProfileEvent.DoesNotExist):
                    print(event.prisoner_profile_event)

    def test_create_events_for_nwn(self):
        credits = Credit.objects.all().order_by('?')[:10]
        for credit in credits:
            credit.amount = random.randint(1, 99) + random.randint(1, 200) * 100
            credit.save()
        disbursements = Disbursement.objects.all().order_by('?')[:10]
        for disbursement in disbursements:
            disbursement.amount = random.randint(1, 99) + random.randint(1, 200) * 100
            disbursement.save()

        for credit in credits:
            triggered = RULES['NWN'].triggered(credit)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['amount'], credit.amount)
            events = RULES['NWN'].create_events(credit)
            self.assertEventMatchesRecord(events, credit)
        self.assertEqual(Event.objects.count(), 10)
        for disbursement in disbursements:
            triggered = RULES['NWN'].triggered(disbursement)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['amount'], disbursement.amount)
            events = RULES['NWN'].create_events(disbursement)
            self.assertEventMatchesRecord(events, disbursement)
        self.assertEqual(Event.objects.count(), 20)

        credits = Credit.objects.filter(amount__endswith='00')
        disbursements = Disbursement.objects.filter(amount__endswith='00')
        for credit in credits:
            triggered = RULES['NWN'].triggered(credit)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['amount'], credit.amount)
        for disbursement in disbursements:
            triggered = RULES['NWN'].triggered(disbursement)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['amount'], disbursement.amount)
        self.assertEqual(Event.objects.count(), 20)

    def test_create_events_for_ha(self):
        credits = Credit.objects.all().order_by('?')[:10]
        for credit in credits:
            credit.amount = random.randint(12000, 200000)
            credit.save()
        disbursements = Disbursement.objects.all().order_by('?')[:10]
        for disbursement in disbursements:
            disbursement.amount = random.randint(12000, 200000)
            disbursement.save()

        for credit in credits:
            triggered = RULES['HA'].triggered(credit)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['amount'], credit.amount)
            events = RULES['HA'].create_events(credit)
            self.assertEventMatchesRecord(events, credit)
        self.assertEqual(Event.objects.count(), 10)
        for disbursement in disbursements:
            triggered = RULES['HA'].triggered(disbursement)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['amount'], disbursement.amount)
            events = RULES['HA'].create_events(disbursement)
            self.assertEventMatchesRecord(events, disbursement)
        self.assertEqual(Event.objects.count(), 20)

        credits = Credit.objects.exclude(amount__gte=12000)
        disbursements = Disbursement.objects.exclude(amount__gte=12000)
        for credit in credits:
            triggered = RULES['HA'].triggered(credit)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['amount'], credit.amount)
        for disbursement in disbursements:
            triggered = RULES['HA'].triggered(disbursement)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['amount'], disbursement.amount)
        self.assertEqual(Event.objects.count(), 20)

    def test_create_events_for_monp_credit(self):
        call_command('update_security_profiles')

        prisoner_profile = PrisonerProfile.objects.filter(credits__isnull=False).first()
        prisoner_profile.monitoring_users.add(self.user)

        credits = Credit.objects.filter(prisoner_profile=prisoner_profile)
        for credit in credits:
            triggered = RULES['MONP'].triggered(credit)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 1)
            events = RULES['MONP'].create_events(credit)
            self.assertEventMatchesRecord(events, credit, PrisonerProfile)

        credits = Credit.objects.exclude(prisoner_profile=prisoner_profile)
        for credit in credits:
            triggered = RULES['MONP'].triggered(credit)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 0)

        self.assertEqual(Event.objects.count(), prisoner_profile.credits.count())

    def test_create_events_for_monp_disbursement(self):
        call_command('update_security_profiles')

        prisoner_profile = PrisonerProfile.objects.filter(disbursements__isnull=False).first()
        prisoner_profile.monitoring_users.add(self.user)

        disbursements = Disbursement.objects.filter(prisoner_profile=prisoner_profile)
        for disbursement in disbursements:
            triggered = RULES['MONP'].triggered(disbursement)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 1)
            events = RULES['MONP'].create_events(disbursement)
            self.assertEventMatchesRecord(events, disbursement, PrisonerProfile)

        disbursements = Disbursement.objects.exclude(prisoner_profile=prisoner_profile)
        for disbursement in disbursements:
            triggered = RULES['MONP'].triggered(disbursement)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 0)

        self.assertEqual(Event.objects.count(), prisoner_profile.disbursements.count())

    def test_create_events_for_mons_debit_card(self):
        call_command('update_security_profiles')

        sender_profile = SenderProfile.objects.filter(
            credits__isnull=False,
            debit_card_details__isnull=False,
        ).first()
        sender_profile.debit_card_details.first().monitoring_users.add(
            self.user
        )

        credits = Credit.objects.filter(sender_profile=sender_profile)
        for credit in credits:
            triggered = RULES['MONS'].triggered(credit)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 1)
            events = RULES['MONS'].create_events(credit)
            self.assertEventMatchesRecord(events, credit, SenderProfile)

        credits = Credit.objects.exclude(sender_profile=sender_profile)
        for credit in credits:
            triggered = RULES['MONS'].triggered(credit)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 0)

        self.assertEqual(Event.objects.count(), sender_profile.credits.count())

    def test_create_events_for_mons_bank_account(self):
        call_command('update_security_profiles')

        sender_profile = SenderProfile.objects.filter(
            credits__isnull=False,
            bank_transfer_details__isnull=False,
        ).first()
        sender_profile.bank_transfer_details.first().sender_bank_account.monitoring_users.add(
            self.user
        )

        credits = Credit.objects.filter(sender_profile=sender_profile)
        for credit in credits:
            triggered = RULES['MONS'].triggered(credit)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 1)
            events = RULES['MONS'].create_events(credit)
            self.assertEventMatchesRecord(events, credit, SenderProfile)

        credits = Credit.objects.exclude(sender_profile=sender_profile)
        for credit in credits:
            triggered = RULES['MONS'].triggered(credit)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 0)

        self.assertEqual(Event.objects.count(), sender_profile.credits.count())

    def test_create_events_for_monr(self):
        call_command('update_security_profiles')

        recipient_profile = RecipientProfile.objects.filter(
            disbursements__isnull=False,
            bank_transfer_details__isnull=False,
        ).first()
        recipient_profile.bank_transfer_details.first().recipient_bank_account.monitoring_users.add(
            self.user
        )

        disbursements = Disbursement.objects.filter(recipient_profile=recipient_profile)
        for disbursement in disbursements:
            triggered = RULES['MONR'].triggered(disbursement)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 1)
            events = RULES['MONR'].create_events(disbursement)
            self.assertEventMatchesRecord(events, disbursement, RecipientProfile)

        disbursements = Disbursement.objects.exclude(recipient_profile=recipient_profile)
        for disbursement in disbursements:
            triggered = RULES['MONR'].triggered(disbursement)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 0)

        self.assertEqual(Event.objects.count(), recipient_profile.disbursements.count())


class CountingRuleTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.today = timezone.now()

        # ensure shared catch-all profiles exist
        self.anonymous_sender = SenderProfile.objects.create()
        self.cheque_recipient = RecipientProfile.objects.create()
        for rule in RULES.values():
            if 'shared_profile' in rule.__dict__:
                del rule.__dict__['shared_profile']

    def make_sender(self):
        sender = SenderProfile.objects.create()
        mommy.make(
            DebitCardSenderDetails,
            sender=sender,
            card_number_last_digits=fake.credit_card_number()[-4:],
            card_expiry_date=fake.credit_card_expire(),
            postcode=fake.postcode(),
        )
        return sender

    def make_recipient(self):
        recipient = RecipientProfile.objects.create()
        bank_account = mommy.make(
            BankAccount,
            sort_code=get_random_string(6, '1234567890'),
            account_number=get_random_string(8, '1234567890'),
        )
        mommy.make(BankTransferRecipientDetails, recipient=recipient, recipient_bank_account=bank_account)
        return recipient

    def make_prisoner(self):
        return mommy.make(
            PrisonerProfile,
            prisoner_name=random_prisoner_name(),
            prisoner_number=random_prisoner_number(),
            prisoner_dob=random_prisoner_dob(),
            current_prison=Prison.objects.order_by('?').first(),
        )

    def make_csfreq_credits(self, sender, count):
        debit_card = sender.debit_card_details.first()
        credit_list = []
        for day in range(count):
            credit = mommy.make(
                Credit,
                sender_profile=sender,
                received_at=self.today - datetime.timedelta(day),
                resolution=CREDIT_RESOLUTION.CREDITED, reconciled=True, private_estate_batch=None,
            )
            if debit_card:
                payment = mommy.make(
                    Payment,
                    card_number_last_digits=debit_card.card_number_last_digits,
                    card_expiry_date=debit_card.card_expiry_date,
                )
                payment.credit = credit
                payment.save()
            credit_list.append(credit)
        return credit_list

    def test_csfreq_rule(self):
        """
        One sender sends many credits
        """
        rule = RULES['CSFREQ']

        # make just enough credits to trigger rule
        count = rule.kwargs['limit'] + 1
        credit_list = self.make_csfreq_credits(self.make_sender(), count)

        # latest credit triggers rule, but all older ones don't
        latest_credit = credit_list[0]
        self.assertTrue(rule.applies_to(latest_credit))
        triggered = rule.triggered(latest_credit)
        self.assertTrue(triggered)
        self.assertEqual(triggered.kwargs['count'], count)
        for older_credit in credit_list[1:]:
            self.assertTrue(rule.applies_to(older_credit))
            self.assertFalse(rule.triggered(older_credit))

        # latest credit stops triggering rule when oldest is too old
        oldest_credit = credit_list[-1]
        oldest_credit.received_at -= datetime.timedelta(days=30)
        oldest_credit.save()
        triggered = rule.triggered(latest_credit)
        self.assertFalse(triggered)
        self.assertEqual(triggered.kwargs['count'], count - 1)

    def make_drfreq_disbursements(self, recipient, count):
        disbursement_list = []
        for day in range(count):
            disbursement = mommy.make(
                Disbursement,
                recipient_profile=recipient,
                created=self.today - datetime.timedelta(day),
                resolution=DISBURSEMENT_RESOLUTION.SENT,
            )
            disbursement_list.append(disbursement)
        return disbursement_list

    def test_drfreq_rule(self):
        """
        One recipient receives many disbursements
        """
        rule = RULES['DRFREQ']

        # make just enough disbursements to trigger rule
        count = rule.kwargs['limit'] + 1
        disbursement_list = self.make_drfreq_disbursements(self.make_recipient(), count)

        # latest disbursement triggers rule, but all older ones don't
        latest_disbursement = disbursement_list[0]
        self.assertTrue(rule.applies_to(latest_disbursement))
        triggered = rule.triggered(latest_disbursement)
        self.assertTrue(triggered)
        self.assertEqual(triggered.kwargs['count'], count)
        for older_disbursement in disbursement_list[1:]:
            self.assertTrue(rule.applies_to(older_disbursement))
            self.assertFalse(rule.triggered(older_disbursement))

        # latest disbursement stops triggering rule when oldest is too old
        oldest_disbursement = disbursement_list[-1]
        oldest_disbursement.created -= datetime.timedelta(days=30)
        oldest_disbursement.save()
        triggered = rule.triggered(latest_disbursement)
        self.assertFalse(triggered)
        self.assertEqual(triggered.kwargs['count'], count - 1)

    def make_csnum_credits(self, prisoner, count, sender_profile=None):
        credit_list = []
        for day in range(count):
            sender = sender_profile or self.make_sender()
            debit_card = sender.debit_card_details.first()
            credit = mommy.make(
                Credit,
                sender_profile=sender,
                prisoner_profile=prisoner,
                received_at=self.today - datetime.timedelta(day),
                resolution=CREDIT_RESOLUTION.CREDITED, reconciled=True, private_estate_batch=None,
            )
            if debit_card:
                payment = mommy.make(
                    Payment,
                    card_number_last_digits=debit_card.card_number_last_digits,
                    card_expiry_date=debit_card.card_expiry_date,
                )
                payment.credit = credit
                payment.save()
            credit_list.append(credit)
        return credit_list

    def test_csnum_rule(self):
        """
        One prisoner receives credits from many senders
        """
        rule = RULES['CSNUM']

        # make just enough credits to trigger rule
        count = rule.kwargs['limit'] + 1
        credit_list = self.make_csnum_credits(self.make_prisoner(), count)

        # latest credit triggers rule, but all older ones don't
        latest_credit = credit_list[0]
        self.assertTrue(rule.applies_to(latest_credit))
        triggered = rule.triggered(latest_credit)
        self.assertTrue(triggered)
        self.assertEqual(triggered.kwargs['count'], count)
        for older_credit in credit_list[1:]:
            self.assertTrue(rule.applies_to(older_credit))
            self.assertFalse(rule.triggered(older_credit))

        # latest credit stops triggering rule when oldest is too old
        oldest_credit = credit_list[-1]
        oldest_credit.received_at -= datetime.timedelta(days=30)
        oldest_credit.save()
        triggered = rule.triggered(latest_credit)
        self.assertFalse(triggered)
        self.assertEqual(triggered.kwargs['count'], count - 1)

        # make extra credits attached to another profile
        self.make_csnum_credits(self.make_prisoner(), 2, sender_profile=latest_credit.sender_profile)
        # latest credit should still not trigger
        self.assertFalse(rule.triggered(latest_credit))

    def make_drnum_disbursements(self, prisoner, count, recipient_profile=None):
        disbursement_list = []
        for day in range(count):
            recipient = recipient_profile or self.make_recipient()
            disbursement = mommy.make(
                Disbursement,
                recipient_profile=recipient,
                prisoner_profile=prisoner,
                created=self.today - datetime.timedelta(day),
                resolution=DISBURSEMENT_RESOLUTION.SENT,
            )
            disbursement_list.append(disbursement)
        return disbursement_list

    def test_drnum_rule(self):
        """
        One prisoner sends disbursements to many recipients
        """
        rule = RULES['DRNUM']

        # make just enough disbursements to trigger rule
        count = rule.kwargs['limit'] + 1
        disbursement_list = self.make_drnum_disbursements(self.make_prisoner(), count)

        # latest disbursement triggers rule, but all older ones don't
        latest_disbursement = disbursement_list[0]
        self.assertTrue(rule.applies_to(latest_disbursement))
        triggered = rule.triggered(latest_disbursement)
        self.assertTrue(triggered)
        self.assertEqual(triggered.kwargs['count'], count)
        for older_disbursement in disbursement_list[1:]:
            self.assertTrue(rule.applies_to(older_disbursement))
            self.assertFalse(rule.triggered(older_disbursement))

        # latest disbursement stops triggering rule when oldest is too old
        oldest_disbursement = disbursement_list[-1]
        oldest_disbursement.created -= datetime.timedelta(days=30)
        oldest_disbursement.save()
        triggered = rule.triggered(latest_disbursement)
        self.assertFalse(triggered)
        self.assertEqual(triggered.kwargs['count'], count - 1)

        # make extra disbursements attached to another profile
        self.make_drnum_disbursements(self.make_prisoner(), 2, recipient_profile=latest_disbursement.recipient_profile)
        # latest disbursement should still not trigger
        self.assertFalse(rule.triggered(latest_disbursement))

    def make_cpnum_credits(self, sender, count, prisoner_profile=None):
        debit_card = sender.debit_card_details.first()
        credit_list = []
        for day in range(count):
            prisoner = prisoner_profile or self.make_prisoner()
            credit = mommy.make(
                Credit,
                sender_profile=sender,
                prisoner_profile=prisoner,
                received_at=self.today - datetime.timedelta(day),
                resolution=CREDIT_RESOLUTION.CREDITED, reconciled=True, private_estate_batch=None,
            )
            if debit_card:
                payment = mommy.make(
                    Payment,
                    card_number_last_digits=debit_card.card_number_last_digits,
                    card_expiry_date=debit_card.card_expiry_date,
                )
                payment.credit = credit
                payment.save()
            credit_list.append(credit)
        return credit_list

    def test_cpnum_rule(self):
        """
        One sender sending credits to many prisoners
        """
        rule = RULES['CPNUM']

        # make just enough credits to trigger rule
        count = rule.kwargs['limit'] + 1
        credit_list = self.make_cpnum_credits(self.make_sender(), count)

        # latest credit triggers rule, but all older ones don't
        latest_credit = credit_list[0]
        self.assertTrue(rule.applies_to(latest_credit))
        triggered = rule.triggered(latest_credit)
        self.assertTrue(triggered)
        self.assertEqual(triggered.kwargs['count'], count)
        for older_credit in credit_list[1:]:
            self.assertTrue(rule.applies_to(older_credit))
            self.assertFalse(rule.triggered(older_credit))

        # latest credit stops triggering rule when oldest is too old
        oldest_credit = credit_list[-1]
        oldest_credit.received_at -= datetime.timedelta(days=30)
        oldest_credit.save()
        triggered = rule.triggered(latest_credit)
        self.assertFalse(triggered)
        self.assertEqual(triggered.kwargs['count'], count - 1)

        # make extra credits attached to another profile
        self.make_cpnum_credits(self.make_sender(), 2, prisoner_profile=latest_credit.prisoner_profile)
        # latest credit should still not trigger
        self.assertFalse(rule.triggered(latest_credit))

    def make_dpnum_disbursements(self, recipient, count, prisoner_profile=None):
        disbursement_list = []
        for day in range(count):
            prisoner = prisoner_profile or self.make_prisoner()
            disbursement = mommy.make(
                Disbursement,
                recipient_profile=recipient,
                prisoner_profile=prisoner,
                created=self.today - datetime.timedelta(day),
                resolution=DISBURSEMENT_RESOLUTION.SENT,
            )
            disbursement_list.append(disbursement)
        return disbursement_list

    def test_dpnum_rule(self):
        """
        One recipient receiving disbursements from many prisoners
        """
        rule = RULES['DPNUM']

        # make just enough disbursements to trigger rule
        count = rule.kwargs['limit'] + 1
        disbursement_list = self.make_dpnum_disbursements(self.make_recipient(), count)

        # latest disbursement triggers rule, but all older ones don't
        latest_disbursement = disbursement_list[0]
        self.assertTrue(rule.applies_to(latest_disbursement))
        triggered = rule.triggered(latest_disbursement)
        self.assertTrue(triggered)
        self.assertEqual(triggered.kwargs['count'], count)
        for older_disbursement in disbursement_list[1:]:
            self.assertTrue(rule.applies_to(older_disbursement))
            self.assertFalse(rule.triggered(older_disbursement))

        # latest disbursement stops triggering rule when oldest is too old
        oldest_disbursement = disbursement_list[-1]
        oldest_disbursement.created -= datetime.timedelta(days=30)
        oldest_disbursement.save()
        triggered = rule.triggered(latest_disbursement)
        self.assertFalse(triggered)
        self.assertEqual(triggered.kwargs['count'], count - 1)

        # make extra disbursements attached to another profile
        self.make_dpnum_disbursements(self.make_recipient(), 2, prisoner_profile=latest_disbursement.prisoner_profile)
        # latest disbursement should still not trigger
        self.assertFalse(rule.triggered(latest_disbursement))

    def test_not_triggered_on_shared_profiles(self):
        """
        Anonymous senders and cheque recipients should not trigger counting rules
        c.f. `update_security_profiles` command
        """
        rule = RULES['CSFREQ']
        # make just enough credits that would normally trigger rule, but should not
        credit_list = self.make_csfreq_credits(self.anonymous_sender, rule.kwargs['limit'] + 1)
        latest_credit = credit_list[0]
        self.assertFalse(rule.triggered(latest_credit))

        rule = RULES['CPNUM']
        # make just enough credits that would normally trigger rule, but should not
        credit_list = self.make_cpnum_credits(self.anonymous_sender, rule.kwargs['limit'] + 1)
        latest_credit = credit_list[0]
        self.assertFalse(rule.triggered(latest_credit))

        rule = RULES['DRFREQ']
        # make just enough disbursements that would normally trigger rule, but should not
        disbursement_list = self.make_drfreq_disbursements(self.cheque_recipient, rule.kwargs['limit'] + 1)
        latest_disbursement = disbursement_list[0]
        self.assertFalse(rule.triggered(latest_disbursement))

        rule = RULES['DPNUM']
        # make just enough disbursements that would normally trigger rule, but should not
        disbursement_list = self.make_dpnum_disbursements(self.cheque_recipient, rule.kwargs['limit'] + 1)
        latest_disbursement = disbursement_list[0]
        self.assertFalse(rule.triggered(latest_disbursement))
