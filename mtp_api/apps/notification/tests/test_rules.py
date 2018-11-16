from datetime import timedelta
from itertools import chain

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.tests.utils import make_test_users
from credit.models import Credit
from disbursement.models import Disbursement
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.tests.utils import generate_disbursements
from notification.models import Subscription, Parameter, Event, EventCredit
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.constants import TIME_PERIOD
from security.models import BankAccount, DebitCardSenderDetails
from transaction.tests.utils import generate_transactions


class RuleTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()
        generate_payments(payment_batch=200, days_of_history=3)
        generate_disbursements(disbursement_batch=200, days_of_history=3)

    def test_create_events_for_nwn(self):
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='NWN', user=user, start=start
        )
        subscription.create_events()

        credits = Credit.objects.exclude(
            amount__endswith='00'
        ).filter(
            created__gte=start
        )
        disbursements = Disbursement.objects.exclude(
            amount__endswith='00'
        ).filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT,
            created__gte=start
        )
        credit_events = [
            event.credits.first() for event in
            Event.objects.filter(credits__isnull=False)
        ]
        disbursement_events = [
            event.disbursements.first() for event in
            Event.objects.filter(disbursements__isnull=False)
        ]

        self.assertEqual(
            set(credits),
            set(credit_events)
        )
        self.assertEqual(
            set(disbursements),
            set(disbursement_events)
        )

    def test_create_events_for_csfreq(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='CSFREQ', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__credit_count__gte', value=5),
            bulk=False
        )
        subscription.create_events()

        credits = Credit.objects.filter(sender_profile__in=Credit.objects.filter(
            created__gte=start,
            sender_profile__totals__time_period=TIME_PERIOD.LAST_7_DAYS,
            sender_profile__totals__credit_count__gte=5
        ).values_list('sender_profile', flat=True).distinct())
        credit_events = list(chain(*[
            event.credits.all() for event in
            Event.objects.filter(credits__isnull=False)
        ]))

        self.assertEqual(
            set(credits),
            set(credit_events)
        )

    def test_create_events_for_drfreq(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='DRFREQ', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__disbursement_count__gte', value=5),
            bulk=False
        )
        subscription.create_events()

        disbursements = Disbursement.objects.filter(
            recipient_profile__in=Disbursement.objects.filter(
                created__gte=start,
                recipient_profile__totals__time_period=TIME_PERIOD.LAST_7_DAYS,
                recipient_profile__totals__disbursement_count__gte=5
            ).values_list('recipient_profile', flat=True).distinct()
        )
        disbursement_events = list(chain(*[
            event.disbursements.all() for event in
            Event.objects.filter(disbursements__isnull=False)
        ]))

        self.assertEqual(
            set(disbursements),
            set(disbursement_events)
        )

    def test_create_events_for_csnum(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='CSNUM', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__sender_count__gte', value=3),
            bulk=False
        )
        subscription.create_events()

        credits = Credit.objects.filter(prisoner_profile__in=Credit.objects.filter(
            created__gte=start,
            prisoner_profile__totals__time_period=TIME_PERIOD.LAST_7_DAYS,
            prisoner_profile__totals__sender_count__gte=3
        ).values_list('prisoner_profile', flat=True).distinct())
        credit_events = list(chain(*[
            event.credits.all() for event in
            Event.objects.filter(credits__isnull=False)
        ]))

        self.assertEqual(
            set(credits),
            set(credit_events)
        )

    def test_create_events_for_drnum(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='DRNUM', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__recipient_count__gte', value=3),
            bulk=False
        )
        subscription.create_events()

        disbursements = Disbursement.objects.filter(
            prisoner_profile__in=Disbursement.objects.filter(
                created__gte=start,
                prisoner_profile__totals__time_period=TIME_PERIOD.LAST_7_DAYS,
                prisoner_profile__totals__recipient_count__gte=3
            ).values_list('prisoner_profile', flat=True).distinct()
        )
        disbursement_events = list(chain(*[
            event.disbursements.all() for event in
            Event.objects.filter(disbursements__isnull=False)
        ]))

        self.assertEqual(
            set(disbursements),
            set(disbursement_events)
        )

    def test_create_events_for_cpnum(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='CPNUM', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__prisoner_count__gte', value=3),
            bulk=False
        )
        subscription.create_events()

        credits = Credit.objects.filter(sender_profile__in=Credit.objects.filter(
            created__gte=start,
            sender_profile__totals__time_period=TIME_PERIOD.LAST_7_DAYS,
            sender_profile__totals__prisoner_count__gte=3
        ).values_list('sender_profile', flat=True).distinct())
        credit_events = list(chain(*[
            event.credits.all() for event in
            Event.objects.filter(credits__isnull=False)
        ]))

        self.assertEqual(
            set(credits),
            set(credit_events)
        )

    def test_create_events_for_dpnum(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='DPNUM', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__prisoner_count__gte', value=3),
            bulk=False
        )
        subscription.create_events()

        disbursements = Disbursement.objects.filter(
            recipient_profile__in=Disbursement.objects.filter(
                created__gte=start,
                recipient_profile__totals__time_period=TIME_PERIOD.LAST_7_DAYS,
                recipient_profile__totals__prisoner_count__gte=3
            ).values_list('recipient_profile', flat=True).distinct()
        )
        disbursement_events = list(chain(*[
            event.disbursements.all() for event in
            Event.objects.filter(disbursements__isnull=False)
        ]))

        self.assertEqual(
            set(disbursements),
            set(disbursement_events)
        )

    def test_create_events_for_vox(self):
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='VOX', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='amount__gte', value=1000),
            bulk=False
        )
        subscription.create_events()

        credits = Credit.objects.filter(
            amount__gte=1000,
            created__gte=start
        )
        disbursements = Disbursement.objects.filter(
            amount__gte=1000,
            created__gte=start,
            resolution=DISBURSEMENT_RESOLUTION.SENT
        )
        credit_events = [
            event.credits.first() for event in
            Event.objects.filter(credits__isnull=False)
        ]
        disbursement_events = [
            event.disbursements.first() for event in
            Event.objects.filter(disbursements__isnull=False)
        ]

        self.assertEqual(
            set(credits),
            set(credit_events)
        )
        self.assertEqual(
            set(disbursements),
            set(disbursement_events)
        )

    def test_does_not_create_new_events_for_triggering_credits(self):
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='VOX', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='amount__gte', value=1000),
            bulk=False
        )
        subscription.create_events()

        old_credit_events = list(Event.objects.filter(credits__isnull=False))
        old_disbursement_events = list(Event.objects.filter(disbursements__isnull=False))

        current_max_event_pk = Event.objects.all().latest('pk').pk
        current_max_credit_pk = Credit.objects.all().latest('pk').pk
        current_max_disbursement_pk = Disbursement.objects.all().latest('pk').pk

        generate_payments(payment_batch=100, days_of_history=3)
        generate_disbursements(disbursement_batch=100, days_of_history=3)
        subscription.create_events()

        new_credit_events = Event.objects.filter(
            credits__isnull=False, pk__gt=current_max_event_pk
        )
        new_disbursement_events = Event.objects.filter(
            disbursements__isnull=False, pk__gt=current_max_event_pk
        )

        for event in new_credit_events:
            self.assertTrue(
                event.credits.first() not in
                Credit.objects.filter(events__in=old_credit_events)
            )
            self.assertGreater(event.credits.first().pk, current_max_credit_pk)

        for event in new_disbursement_events:
            self.assertTrue(
                event.disbursements.first() not in
                Disbursement.objects.filter(events__in=old_disbursement_events)
            )
            self.assertGreater(
                event.disbursements.first().pk, current_max_disbursement_pk
            )

    def test_only_most_recent_record_triggers_event(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='CSNUM', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__sender_count__gte', value=3),
            bulk=False
        )
        subscription.create_events()

        relevant_credits = Credit.objects.filter(
            created__gte=start,
            prisoner_profile__totals__time_period=TIME_PERIOD.LAST_7_DAYS,
            prisoner_profile__totals__sender_count__gte=3
        )

        expected_triggers = set()
        for credit in relevant_credits:
            most_recent_credit = Credit.objects.filter(
                prisoner_profile=credit.prisoner_profile
            ).order_by('-created').first()
            if credit.id == most_recent_credit.id:
                expected_triggers.add(credit)

        triggering_credits = set(
            e.credit for e in EventCredit.objects.filter(triggering=True)
        )

        self.assertEqual(
            len(expected_triggers),
            len(Event.objects.all())
        )
        self.assertEqual(expected_triggers, triggering_credits)

    def test_event_description_for_time_period_rule(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='CSNUM', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__sender_count__gte', value=3),
            bulk=False
        )
        subscription.create_events()

        for event in Event.objects.all():
            self.assertEqual(
                'A prisoner getting money from more than 3 '
                'debit cards or bank accounts in last 7 days',
                event.description
            )

    def test_event_description_for_combined_rule(self):
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='VOX', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='amount__gte', value=1000),
            bulk=False
        )
        subscription.create_events()

        for event in Event.objects.all():
            self.assertEqual('Credits or disbursements over £10', event.description)

    def test_create_events_for_monitored_bank_account(self):
        generate_transactions(transaction_batch=200, days_of_history=3)
        call_command('update_security_profiles')
        user = self.security_staff[0]

        bank_account = BankAccount.objects.first()
        bank_account.monitoring_users.add(user)

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='MON', user=user, start=start
        )
        subscription.create_events()

        credits = Credit.objects.filter(
            sender_profile__bank_transfer_details__sender_bank_account=bank_account
        )
        disbursements = Disbursement.objects.filter(
            recipient_profile__bank_transfer_details__recipient_bank_account=bank_account
        )
        credit_events = list(chain(*[
            event.credits.all() for event in
            Event.objects.filter(credits__isnull=False)
        ]))
        disbursement_events = list(chain(*[
            event.disbursements.all() for event in
            Event.objects.filter(disbursements__isnull=False)
        ]))

        self.assertEqual(
            set(credits),
            set(credit_events)
        )
        self.assertEqual(
            set(disbursements),
            set(disbursement_events)
        )

    def test_create_events_for_monitored_prisoner(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        prisoner = Credit.objects.filter(prisoner_profile__isnull=False
            ).first().prisoner_profile
        prisoner.monitoring_users.add(user)

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='MON', user=user, start=start
        )
        subscription.create_events()

        credits = Credit.objects.filter(
            prisoner_number=prisoner.prisoner_number
        )
        disbursements = Disbursement.objects.filter(
            resolution=DISBURSEMENT_RESOLUTION.SENT,
            prisoner_number=prisoner.prisoner_number
        )
        credit_events = list(chain(*[
            event.credits.all() for event in
            Event.objects.filter(credits__isnull=False)
        ]))
        disbursement_events = list(chain(*[
            event.disbursements.all() for event in
            Event.objects.filter(disbursements__isnull=False)
        ]))

        self.assertEqual(
            set(credits),
            set(credit_events)
        )
        self.assertEqual(
            set(disbursements),
            set(disbursement_events)
        )

    def test_create_events_for_monitored_debit_card(self):
        call_command('update_security_profiles')
        user = self.security_staff[0]

        debit_card = DebitCardSenderDetails.objects.first()
        debit_card.monitoring_users.add(user)

        start = timezone.now() - timedelta(days=2)
        subscription = Subscription.objects.create(
            rule='MON', user=user, start=start
        )
        subscription.create_events()

        credits = Credit.objects.filter(
            sender_profile__debit_card_details=debit_card
        )
        credit_events = list(chain(*[
            event.credits.all() for event in
            Event.objects.filter(credits__isnull=False)
        ]))

        self.assertEqual(
            set(credits),
            set(credit_events)
        )
