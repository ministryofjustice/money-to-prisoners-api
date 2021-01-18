import datetime
import random

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.tests.utils import make_test_users
from credit.models import Credit
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from notification.models import (
    SenderProfileEvent, RecipientProfileEvent, PrisonerProfileEvent
)
from notification.rules import Event, RULES
from notification.tests.utils import (
    make_sender, make_recipient, make_prisoner,
    make_csfreq_credits, make_drfreq_disbursements,
    make_csnum_credits, make_drnum_disbursements,
    make_cpnum_credits, make_dpnum_disbursements,
)
from payment.models import Payment
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import SenderProfile, RecipientProfile, PrisonerProfile
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions


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

    def test_fiu_rules(self):
        call_command('update_security_profiles')

        security_group = Group.objects.get(name='Security')
        fiu_group = Group.objects.get(name='FIU')
        for security_user in security_group.user_set.all():
            security_user.groups.add(fiu_group)

        prisoner_profile = PrisonerProfile.objects.filter(credits__isnull=False).first()
        prisoner_profile.monitoring_users.add(self.user)

        credits = Credit.objects.filter(prisoner_profile=prisoner_profile)
        for credit in credits:
            triggered = RULES['FIUMONP'].triggered(credit)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 1)
            events = RULES['FIUMONP'].create_events(credit)
            self.assertEventMatchesRecord(events, credit, PrisonerProfile)

        # ensures that monitoring_user_count is properly counted
        security_user_count = security_group.user_set.count()
        for security_user in security_group.user_set.all():
            prisoner_profile.monitoring_users.add(security_user)
        for credit in credits:
            triggered = RULES['FIUMONP'].triggered(credit)
            self.assertTrue(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], security_user_count)

        credits = Credit.objects.exclude(prisoner_profile=prisoner_profile)
        for credit in credits:
            triggered = RULES['FIUMONP'].triggered(credit)
            self.assertFalse(triggered)
            self.assertEqual(triggered.kwargs['monitoring_user_count'], 0)

        self.assertEqual(Event.objects.count(), prisoner_profile.credits.count())


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

    def test_csfreq_rule(self):
        """
        One sender sends many credits
        """
        rule = RULES['CSFREQ']

        # make just enough credits to trigger rule
        count = rule.kwargs['limit'] + 1
        credit_list = make_csfreq_credits(self.today, make_sender(), count)

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

    def test_drfreq_rule(self):
        """
        One recipient receives many disbursements
        """
        rule = RULES['DRFREQ']

        # make just enough disbursements to trigger rule
        count = rule.kwargs['limit'] + 1
        disbursement_list = make_drfreq_disbursements(self.today, make_recipient(), count)

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

    def test_csnum_rule(self):
        """
        One prisoner receives credits from many senders
        """
        rule = RULES['CSNUM']

        # make just enough credits to trigger rule
        count = rule.kwargs['limit'] + 1
        credit_list = make_csnum_credits(self.today, make_prisoner(), count)

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
        make_csnum_credits(
            self.today, make_prisoner(), 2, sender_profile=latest_credit.sender_profile
        )
        # latest credit should still not trigger
        self.assertFalse(rule.triggered(latest_credit))

    def test_drnum_rule(self):
        """
        One prisoner sends disbursements to many recipients
        """
        rule = RULES['DRNUM']

        # make just enough disbursements to trigger rule
        count = rule.kwargs['limit'] + 1
        disbursement_list = make_drnum_disbursements(self.today, make_prisoner(), count)

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
        make_drnum_disbursements(
            self.today, make_prisoner(), 2, recipient_profile=latest_disbursement.recipient_profile
        )
        # latest disbursement should still not trigger
        self.assertFalse(rule.triggered(latest_disbursement))

    def test_cpnum_rule(self):
        """
        One sender sending credits to many prisoners
        """
        rule = RULES['CPNUM']

        # make just enough credits to trigger rule
        count = rule.kwargs['limit'] + 1
        credit_list = make_cpnum_credits(self.today, make_sender(), count)

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
        make_cpnum_credits(
            self.today, make_sender(), 2, prisoner_profile=latest_credit.prisoner_profile
        )
        # latest credit should still not trigger
        self.assertFalse(rule.triggered(latest_credit))

    def test_dpnum_rule(self):
        """
        One recipient receiving disbursements from many prisoners
        """
        rule = RULES['DPNUM']

        # make just enough disbursements to trigger rule
        count = rule.kwargs['limit'] + 1
        disbursement_list = make_dpnum_disbursements(self.today, make_recipient(), count)

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
        make_dpnum_disbursements(
            self.today, make_recipient(), 2, prisoner_profile=latest_disbursement.prisoner_profile
        )
        # latest disbursement should still not trigger
        self.assertFalse(rule.triggered(latest_disbursement))

    def test_not_triggered_on_shared_profiles(self):
        """
        Anonymous senders and cheque recipients should not trigger counting rules
        c.f. `update_security_profiles` command
        """
        rule = RULES['CSFREQ']
        # make just enough credits that would normally trigger rule, but should not
        credit_list = make_csfreq_credits(self.today, self.anonymous_sender, rule.kwargs['limit'] + 1)
        latest_credit = credit_list[0]
        self.assertFalse(rule.triggered(latest_credit))

        rule = RULES['CPNUM']
        # make just enough credits that would normally trigger rule, but should not
        credit_list = make_cpnum_credits(self.today, self.anonymous_sender, rule.kwargs['limit'] + 1)
        latest_credit = credit_list[0]
        self.assertFalse(rule.triggered(latest_credit))

        rule = RULES['DRFREQ']
        # make just enough disbursements that would normally trigger rule, but should not
        disbursement_list = make_drfreq_disbursements(self.today, self.cheque_recipient, rule.kwargs['limit'] + 1)
        latest_disbursement = disbursement_list[0]
        self.assertFalse(rule.triggered(latest_disbursement))

        rule = RULES['DPNUM']
        # make just enough disbursements that would normally trigger rule, but should not
        disbursement_list = make_dpnum_disbursements(self.today, self.cheque_recipient, rule.kwargs['limit'] + 1)
        latest_disbursement = disbursement_list[0]
        self.assertFalse(rule.triggered(latest_disbursement))


class ContainsSymbolsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users(clerks_per_prison=1)
        load_random_prisoner_locations(number_of_prisoners=1)
        generate_transactions(transaction_batch=1)
        generate_payments(payment_batch=1)

    def test_credits_with_symbols(self):
        rule = RULES['CSYM']

        name_with_symbols = 'James ❤️ Halls'
        for transaction in Transaction.objects.all():
            transaction.sender_name = name_with_symbols
            transaction.save()
        for payment in Payment.objects.all():
            payment.cardholder_name = name_with_symbols
            payment.save()
        for credit in Credit.objects.all():
            self.assertTrue(
                rule.triggered(credit),
                msg=f'Credit from {credit.sender_name} should trigger',
            )

        name_without_symbols = 'James-Halls'  # simple punctation is allowed
        for transaction in Transaction.objects.all():
            transaction.sender_name = name_without_symbols
            transaction.save()
        for payment in Payment.objects.all():
            payment.cardholder_name = name_without_symbols
            payment.save()
        for credit in Credit.objects.all():
            self.assertFalse(
                rule.triggered(credit),
                msg=f'Credit from {credit.sender_name} should not trigger',
            )
