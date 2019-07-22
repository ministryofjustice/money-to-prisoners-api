from django.core.management import call_command
from django.test import TestCase

from core.tests.utils import make_test_users
from credit.models import Credit
from disbursement.models import Disbursement
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.tests.utils import generate_disbursements
from notification.models import (
    SenderProfileEvent, RecipientProfileEvent, PrisonerProfileEvent
)
from notification.rules import RULES
from payment.models import Payment
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import (
    SenderProfile, RecipientProfile, PrisonerProfile
)
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
        credits = Credit.objects.exclude(
            amount__endswith='00'
        )
        disbursements = Disbursement.objects.exclude(
            amount__endswith='00'
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT,
        )

        for credit in credits:
            self.assertTrue(RULES['NWN'].triggered(credit))
            events = RULES['NWN'].create_events(credit)
            self.assertEventMatchesRecord(events, credit)
        for disbursement in disbursements:
            self.assertTrue(RULES['NWN'].triggered(disbursement))
            events = RULES['NWN'].create_events(disbursement)
            self.assertEventMatchesRecord(events, disbursement)

        credits = Credit.objects.filter(
            amount__endswith='00'
        )
        disbursements = Disbursement.objects.filter(
            amount__endswith='00'
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT,
        )

        for credit in credits:
            self.assertFalse(RULES['NWN'].triggered(credit))
        for disbursement in disbursements:
            self.assertFalse(RULES['NWN'].triggered(disbursement))

    def test_create_events_for_ha(self):
        credits = Credit.objects.filter(
            amount__gte=12000
        )
        disbursements = Disbursement.objects.filter(
            amount__gte=12000,
            resolution=DISBURSEMENT_RESOLUTION.SENT
        )
        for credit in credits:
            self.assertTrue(RULES['HA'].triggered(credit))
            events = RULES['HA'].create_events(credit)
            self.assertEventMatchesRecord(events, credit)
        for disbursement in disbursements:
            self.assertTrue(RULES['HA'].triggered(disbursement))
            events = RULES['HA'].create_events(disbursement)
            self.assertEventMatchesRecord(events, disbursement)

        credits = Credit.objects.exclude(
            amount__gte=12000
        )
        disbursements = Disbursement.objects.exclude(
            amount__gte=12000
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT
        )
        for credit in credits:
            self.assertFalse(RULES['HA'].triggered(credit))
        for disbursement in disbursements:
            self.assertFalse(RULES['HA'].triggered(disbursement))

    def test_create_events_for_monp(self):
        call_command('update_security_profiles')

        prisoner_profile = PrisonerProfile.objects.filter(
            credits__isnull=False,
            disbursements__isnull=False
        ).first()

        prisoner_profile.monitoring_users.add(self.user)

        credits = Credit.objects.filter(
            prisoner_profile=prisoner_profile
        )
        disbursements = Disbursement.objects.filter(
            prisoner_profile=prisoner_profile
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT,
        )

        for credit in credits:
            self.assertTrue(RULES['MONP'].triggered(credit))
            events = RULES['MONP'].create_events(credit)
            self.assertEventMatchesRecord(events, credit, PrisonerProfile)
        for disbursement in disbursements:
            self.assertTrue(RULES['MONP'].triggered(disbursement))
            events = RULES['MONP'].create_events(disbursement)
            self.assertEventMatchesRecord(events, disbursement, PrisonerProfile)

        credits = Credit.objects.exclude(
            prisoner_profile=prisoner_profile
        )
        disbursements = Disbursement.objects.exclude(
            prisoner_profile=prisoner_profile
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT,
        )

        for credit in credits:
            self.assertFalse(RULES['MONP'].triggered(credit))
        for disbursement in disbursements:
            self.assertFalse(RULES['MONP'].triggered(disbursement))

    def test_create_events_for_mons_debit_card(self):
        call_command('update_security_profiles')

        sender_profile = SenderProfile.objects.filter(
            credits__isnull=False,
            debit_card_details__isnull=False
        ).first()

        sender_profile.debit_card_details.first().monitoring_users.add(
            self.user
        )

        credits = Credit.objects.filter(
            sender_profile=sender_profile
        )

        for credit in credits:
            self.assertTrue(RULES['MONS'].triggered(credit))
            events = RULES['MONS'].create_events(credit)
            self.assertEventMatchesRecord(events, credit, SenderProfile)

        credits = Credit.objects.exclude(
            sender_profile=sender_profile
        )

        for credit in credits:
            self.assertFalse(RULES['MONS'].triggered(credit))

    def test_create_events_for_mons_bank_account(self):
        call_command('update_security_profiles')

        sender_profile = SenderProfile.objects.filter(
            credits__isnull=False,
            bank_transfer_details__isnull=False
        ).first()

        sender_profile.bank_transfer_details.first().sender_bank_account.monitoring_users.add(
            self.user
        )

        credits = Credit.objects.filter(
            sender_profile=sender_profile
        )

        for credit in credits:
            self.assertTrue(RULES['MONS'].triggered(credit))
            events = RULES['MONS'].create_events(credit)
            self.assertEventMatchesRecord(events, credit, SenderProfile)

        credits = Credit.objects.exclude(
            sender_profile=sender_profile
        )

        for credit in credits:
            self.assertFalse(RULES['MONS'].triggered(credit))

    def test_create_events_for_monr(self):
        call_command('update_security_profiles')

        recipient_profile = RecipientProfile.objects.filter(
            disbursements__isnull=False,
            bank_transfer_details__isnull=False
        ).first()

        recipient_profile.bank_transfer_details.first().recipient_bank_account.monitoring_users.add(
            self.user
        )

        disbursements = Disbursement.objects.filter(
            recipient_profile=recipient_profile
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT,
        )

        for disbursement in disbursements:
            self.assertTrue(RULES['MONR'].triggered(disbursement))
            events = RULES['MONR'].create_events(disbursement)
            self.assertEventMatchesRecord(events, disbursement, RecipientProfile)

        disbursements = Disbursement.objects.exclude(
            recipient_profile=recipient_profile
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT,
        )

        for disbursement in disbursements:
            self.assertFalse(RULES['MONR'].triggered(disbursement))
