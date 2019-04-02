from django.core.management import call_command
from django.test import TestCase

from core.tests.utils import make_test_users
from credit.models import Credit
from disbursement.models import Disbursement
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.tests.utils import generate_disbursements
from notification.models import (
    Event, SenderProfileEvent, RecipientProfileEvent, PrisonerProfileEvent
)
from notification.rules import RULES
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.constants import TIME_PERIOD
from security.models import (
    SenderProfile, RecipientProfile, PrisonerProfile
)


class RuleTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()
        generate_payments(payment_batch=200, days_of_history=3)
        generate_disbursements(disbursement_batch=200, days_of_history=3)

    def assert_event_matches_record(self, event, record, profile_class=None):
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
                event.sender_profile_event

        if profile_class == RecipientProfile:
            self.assertEqual(
                event.recipient_profile_event.recipient_profile,
                record.recipient_profile
            )
        else:
            with self.assertRaises(RecipientProfileEvent.DoesNotExist):
                event.recipient_profile_event

        if profile_class == PrisonerProfile:
            self.assertEqual(
                event.prisoner_profile_event.prisoner_profile,
                record.prisoner_profile
            )
        else:
            with self.assertRaises(PrisonerProfileEvent.DoesNotExist):
                event.prisoner_profile_event

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
            event = RULES['NWN'].create_event(credit)
            self.assert_event_matches_record(event, credit)
        for disbursement in disbursements:
            self.assertTrue(RULES['NWN'].triggered(disbursement))
            event = RULES['NWN'].create_event(disbursement)
            self.assert_event_matches_record(event, disbursement)

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

    def test_create_events_for_csfreq(self):
        call_command('update_security_profiles')

        credits = Credit.objects.filter(sender_profile__in=Credit.objects.filter(
            sender_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
            sender_profile__totals__credit_count__gte=4
        ).values_list('sender_profile', flat=True).distinct())
        for credit in credits:
            self.assertTrue(RULES['CSFREQ'].triggered(credit))
            event = RULES['CSFREQ'].create_event(credit)
            self.assert_event_matches_record(event, credit, SenderProfile)

        credits = Credit.objects.exclude(sender_profile__in=Credit.objects.filter(
            sender_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
            sender_profile__totals__credit_count__gte=4
        ).values_list('sender_profile', flat=True).distinct())
        for credit in credits:
            self.assertFalse(RULES['CSFREQ'].triggered(credit))

    def test_create_events_for_drfreq(self):
        call_command('update_security_profiles')

        disbursements = Disbursement.objects.filter(
            recipient_profile__in=Disbursement.objects.filter(
                recipient_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
                recipient_profile__totals__disbursement_count__gte=4
            ).values_list('recipient_profile', flat=True).distinct()
        )
        for disbursement in disbursements:
            self.assertTrue(RULES['DRFREQ'].triggered(disbursement))
            event = RULES['DRFREQ'].create_event(disbursement)
            self.assert_event_matches_record(event, disbursement, RecipientProfile)

        disbursements = Disbursement.objects.exclude(
            recipient_profile__in=Disbursement.objects.filter(
                recipient_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
                recipient_profile__totals__disbursement_count__gte=4
            ).values_list('recipient_profile', flat=True).distinct()
        )
        for disbursement in disbursements:
            self.assertFalse(RULES['DRFREQ'].triggered(disbursement))

    def test_create_events_for_csnum(self):
        call_command('update_security_profiles')

        credits = Credit.objects.filter(prisoner_profile__in=Credit.objects.filter(
            prisoner_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
            prisoner_profile__totals__sender_count__gte=4
        ).values_list('prisoner_profile', flat=True).distinct())
        for credit in credits:
            self.assertTrue(RULES['CSNUM'].triggered(credit))
            event = RULES['CSNUM'].create_event(credit)
            self.assert_event_matches_record(event, credit, PrisonerProfile)

        credits = Credit.objects.exclude(prisoner_profile__in=Credit.objects.filter(
            prisoner_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
            prisoner_profile__totals__sender_count__gte=4
        ).values_list('prisoner_profile', flat=True).distinct())
        for credit in credits:
            self.assertFalse(RULES['CSNUM'].triggered(credit))

    def test_create_events_for_drnum(self):
        call_command('update_security_profiles')

        disbursements = Disbursement.objects.filter(
            prisoner_profile__in=Disbursement.objects.filter(
                prisoner_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
                prisoner_profile__totals__recipient_count__gte=4
            ).values_list('prisoner_profile', flat=True).distinct()
        )
        for disbursement in disbursements:
            self.assertTrue(RULES['DRNUM'].triggered(disbursement))
            event = RULES['DRNUM'].create_event(disbursement)
            self.assert_event_matches_record(event, disbursement, PrisonerProfile)

        disbursements = Disbursement.objects.exclude(
            prisoner_profile__in=Disbursement.objects.filter(
                prisoner_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
                prisoner_profile__totals__recipient_count__gte=4
            ).values_list('prisoner_profile', flat=True).distinct()
        )
        for disbursement in disbursements:
            self.assertFalse(RULES['DRNUM'].triggered(disbursement))

    def test_create_events_for_cpnum(self):
        call_command('update_security_profiles')

        credits = Credit.objects.filter(sender_profile__in=Credit.objects.filter(
            sender_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
            sender_profile__totals__prisoner_count__gte=4
        ).values_list('sender_profile', flat=True).distinct())
        for credit in credits:
            self.assertTrue(RULES['CPNUM'].triggered(credit))
            event = RULES['CPNUM'].create_event(credit)
            self.assert_event_matches_record(event, credit, SenderProfile)

        credits = Credit.objects.exclude(sender_profile__in=Credit.objects.filter(
            sender_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
            sender_profile__totals__prisoner_count__gte=4
        ).values_list('sender_profile', flat=True).distinct())
        for credit in credits:
            self.assertFalse(RULES['CPNUM'].triggered(credit))

    def test_create_events_for_dpnum(self):
        call_command('update_security_profiles')

        disbursements = Disbursement.objects.filter(
            recipient_profile__in=Disbursement.objects.filter(
                recipient_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
                recipient_profile__totals__prisoner_count__gte=4
            ).values_list('recipient_profile', flat=True).distinct()
        )
        for disbursement in disbursements:
            self.assertTrue(RULES['DPNUM'].triggered(disbursement))
            event = RULES['DPNUM'].create_event(disbursement)
            self.assert_event_matches_record(event, disbursement, RecipientProfile)

        disbursements = Disbursement.objects.exclude(
            recipient_profile__in=Disbursement.objects.filter(
                recipient_profile__totals__time_period=TIME_PERIOD.LAST_30_DAYS,
                recipient_profile__totals__prisoner_count__gte=4
            ).values_list('recipient_profile', flat=True).distinct()
        )
        for disbursement in disbursements:
            self.assertFalse(RULES['DPNUM'].triggered(disbursement))

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
            event = RULES['HA'].create_event(credit)
            self.assert_event_matches_record(event, credit)
        for disbursement in disbursements:
            self.assertTrue(RULES['HA'].triggered(disbursement))
            event = RULES['HA'].create_event(disbursement)
            self.assert_event_matches_record(event, disbursement)

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

    def test_event_description_for_time_period_rule(self):
        call_command('update_security_profiles')

        for event in Event.objects.filter(rule='CSNUM'):
            self.assertEqual(
                'A prisoner getting money from more than 4 '
                'debit cards or bank accounts in last 30 days',
                event.description
            )
