import itertools
from datetime import timedelta
import unittest

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from faker import Faker
from model_mommy import mommy
from rest_framework import status
from rest_framework.test import APITestCase

from notification.constants import EMAIL_FREQUENCY
from notification.models import Event, EmailNotificationPreferences
from notification.rules import RULES, ENABLED_RULE_CODES
from core.tests.utils import make_test_users
from credit.models import Credit
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import PrisonerProfile, SenderProfile
from transaction.tests.utils import generate_transactions

fake = Faker(locale='en_GB')


class ListRuleViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']

    def test_get_rules(self):
        user = self.security_staff[0]

        response = self.client.get(
            reverse('rule-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rules = [
            {'code': code, 'description': RULES[code].description}
            for code in RULES
            if code in ENABLED_RULE_CODES
        ]
        self.assertDictEqual(response.data, {
            'count': len(ENABLED_RULE_CODES),
            'results': rules,
            'next': None,
            'previous': None,
        })


class ListEventPagesTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.user = test_users['security_staff'][0]

    def assertApiResponse(self, data, expected_response):  # noqa: N802
        response = self.client.get(
            reverse('event-pages'), data, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertDictEqual(response.data, expected_response)

    def test_empty_page_list(self):
        """
        Empty response when no events
        """
        self.assertFalse(Event.objects.exists())

        self.assertApiResponse({'limit': 25}, {'count': 0, 'newest': None, 'oldest': None})

    def test_one_event_page_list(self):
        """
        One event returns one date
        """
        yesterday = timezone.now() - timedelta(days=1)
        mommy.make(Event, user=self.user, triggered_at=yesterday)
        self.assertEqual(Event.objects.count(), 1)
        yesterday = yesterday.date()

        self.assertApiResponse({'limit': 25}, {
            'count': 1,
            'newest': yesterday,
            'oldest': yesterday,
        })

    def test_many_event_page_list(self):
        """
        Many events on one date returns one date
        """
        some_date = timezone.now() - timedelta(days=5)
        some_date = some_date.replace(hour=12, minute=0, second=0)
        for hour in range(0, 5):
            mommy.make(Event, user=self.user, triggered_at=some_date + timedelta(hours=hour))
        self.assertEqual(Event.objects.count(), 5)
        some_date = some_date.date()

        self.assertApiResponse({'limit': 25}, {
            'count': 1,
            'newest': some_date,
            'oldest': some_date,
        })

    def test_many_date_page_list(self):
        """
        Events on various dates return the range
        """
        dates = set()
        for _ in range(0, 25):
            event = mommy.make(
                Event, user=self.user,
                triggered_at=timezone.make_aware(fake.date_time_between(start_date='-10w', end_date='-1d')),
            )
            dates.add(event.triggered_at.date())
        self.assertEqual(Event.objects.count(), 25)
        dates = sorted(dates)

        self.assertApiResponse({'limit': 25}, {
            'count': len(dates),
            'newest': dates[-1],
            'oldest': dates[0],
        })

    def test_long_date_page_list(self):
        """
        Events over a larger range of dates than requested, get the appropriate page
        """
        yesterday = timezone.now() - timedelta(days=1)
        date = yesterday
        for _ in range(0, 30):
            mommy.make(Event, user=self.user, triggered_at=date)
            date -= timedelta(days=1)
        self.assertEqual(Event.objects.count(), 30)
        yesterday = yesterday.date()

        self.assertApiResponse({'limit': 25, 'offset': 0}, {
            'count': 30,
            'newest': yesterday,
            'oldest': yesterday - timedelta(days=24),
        })
        self.assertApiResponse({'limit': 25, 'offset': 25}, {
            'count': 30,
            'newest': yesterday - timedelta(days=25),
            'oldest': yesterday - timedelta(days=29),
        })

    def test_filtered_long_date_page_list(self):
        """
        Events over a larger range of dates than requested, get the appropriate page filtered by rule
        """
        yesterday = timezone.now() - timedelta(days=1)
        date = yesterday
        for rule in itertools.islice(itertools.cycle(['MONP', 'MONS']), 100):
            mommy.make(Event, rule=rule, user=self.user, triggered_at=date)
            date -= timedelta(days=1)
        self.assertEqual(Event.objects.count(), 100)
        self.assertEqual(Event.objects.filter(rule='MONP').count(), 50)
        yesterday = yesterday.date()

        # page 1 filtering by all rules
        self.assertApiResponse({
            'limit': 25, 'offset': 0,
            'rule': ['MONS', 'MONP'],
        }, {
            'count': 100,
            'newest': yesterday,
            'oldest': yesterday - timedelta(days=24),
        })
        # page 1 filtering by one rule
        self.assertApiResponse({
            'limit': 25, 'offset': 0,
            'rule': ['MONP'],
        }, {
            'count': 50,
            'newest': yesterday,
            'oldest': yesterday - timedelta(days=48),
        })

        # page 2 filtering by all rules
        self.assertApiResponse({
            'limit': 25, 'offset': 25,
            'rule': ['MONS', 'MONP'],
        }, {
            'count': 100,
            'newest': yesterday - timedelta(days=25),
            'oldest': yesterday - timedelta(days=49),
        })
        # page 2 filtering by one rule
        self.assertApiResponse({
            'limit': 25, 'offset': 25,
            'rule': 'MONP',
        }, {
            'count': 50,
            'newest': yesterday - timedelta(days=50),
            'oldest': yesterday - timedelta(days=98),
        })
        # page 2 filtering by another rule
        self.assertApiResponse({
            'limit': 25, 'offset': 25,
            'rule': 'MONS',
        }, {
            'count': 50,
            'newest': yesterday - timedelta(days=51),
            'oldest': yesterday - timedelta(days=99),
        })


class ListEventsViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']
        load_random_prisoner_locations()

    def test_get_events(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        user = self.security_staff[0]

        for credit in Credit.objects.all():
            if RULES['HA'].triggered(credit):
                RULES['HA'].create_events(credit)
        for disbursement in Disbursement.objects.filter(resolution=DISBURSEMENT_RESOLUTION.SENT):
            if RULES['HA'].triggered(disbursement):
                RULES['HA'].create_events(disbursement)

        response = self.client.get(
            reverse('event-list'), {'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        triggering_credits = Credit.objects.filter(
            amount__gte=12000,
        )
        triggering_disbursements = Disbursement.objects.filter(
            amount__gte=12000, resolution=DISBURSEMENT_RESOLUTION.SENT
        )
        self.assertEqual(
            response.data['count'],
            triggering_credits.count() + triggering_disbursements.count()
        )

    @unittest.skip('rules disabled')
    def test_get_events_filtered_by_rules(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        call_command('update_security_profiles')
        user = self.security_staff[0]

        response = self.client.get(
            reverse('event-list'),
            {'limit': 1000, 'rule': ['HA', 'NWN']},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        self.assertEqual(
            response.data['count'],
            Event.objects.filter(rule='HA').count() +
            Event.objects.filter(rule='NWN').count()
        )
        for event in response.data['results']:
            self.assertIn(event['rule'], ('HA', 'NWN'))

    def test_get_events_filtered_by_date(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        user = self.security_staff[0]

        for credit in Credit.objects.all():
            if RULES['HA'].triggered(credit):
                RULES['HA'].create_events(credit)
        for disbursement in Disbursement.objects.filter(resolution=DISBURSEMENT_RESOLUTION.SENT):
            if RULES['HA'].triggered(disbursement):
                RULES['HA'].create_events(disbursement)

        lt = timezone.now()
        gte = lt - timedelta(days=2)
        response = self.client.get(
            reverse('event-list'),
            {'triggered_at__lt': lt, 'triggered_at__gte': gte, 'limit': 1000},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        self.assertEqual(
            response.data['count'],
            Event.objects.filter(triggered_at__gte=gte, triggered_at__lt=lt).count()
        )

    def test_get_prisoner_monitoring_events_for_user(self):
        generate_payments(payment_batch=200, days_of_history=5)
        call_command('update_security_profiles')
        user = self.security_staff[0]

        prisoner_profile = PrisonerProfile.objects.filter(
            credits__isnull=False,
        ).first()
        prisoner_profile.monitoring_users.add(user)

        for credit in Credit.objects.all():
            if RULES['MONP'].triggered(credit):
                RULES['MONP'].create_events(credit)

        response = self.client.get(
            reverse('event-list'), {'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        self.assertEqual(
            response.data['count'],
            Event.objects.filter(user__isnull=True).count() +
            Event.objects.filter(user=user).count()
        )

        for event in response.data['results']:
            if event['rule'] == 'MONP':
                self.assertEqual(Event.objects.get(id=event['id']).user, user)
            else:
                self.assertEqual(Event.objects.get(id=event['id']).user, None)

    def test_get_sender_monitoring_events_for_user(self):
        generate_payments(payment_batch=200, days_of_history=5)
        call_command('update_security_profiles')
        user = self.security_staff[0]

        sender_profile = SenderProfile.objects.filter(
            credits__isnull=False,
        ).first()
        debit_card = sender_profile.debit_card_details.first()
        bank_transfer = sender_profile.bank_transfer_details.first()
        if debit_card:
            debit_card.monitoring_users.add(user)
        elif bank_transfer:
            bank_transfer.sender_bank_account.monitoring_users.add(user)
        else:
            self.fail('sender profile incomplete')

        for credit in Credit.objects.all():
            if RULES['MONS'].triggered(credit):
                RULES['MONS'].create_events(credit)

        response = self.client.get(
            reverse('event-list'), {'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        self.assertEqual(
            response.data['count'],
            Event.objects.filter(user__isnull=True).count() +
            Event.objects.filter(user=user).count()
        )

        for event in response.data['results']:
            if event['rule'] == 'MONS':
                self.assertEqual(Event.objects.get(id=event['id']).user, user)
            else:
                self.assertEqual(Event.objects.get(id=event['id']).user, None)


class EmailPreferencesViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']

    def test_set_frequency(self):
        user = self.security_staff[0]

        response = self.client.post(
            reverse('emailpreferences-list'), {'frequency': EMAIL_FREQUENCY.DAILY},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            EmailNotificationPreferences.objects.get(user=user).frequency,
            EMAIL_FREQUENCY.DAILY
        )

    def test_unset_frequency(self):
        user = self.security_staff[0]
        EmailNotificationPreferences.objects.create(
            user=user, frequency=EMAIL_FREQUENCY.DAILY
        )

        response = self.client.post(
            reverse('emailpreferences-list'), {'frequency': EMAIL_FREQUENCY.NEVER},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            EmailNotificationPreferences.objects.filter(user=user).count(), 0
        )

    def test_get_frequency(self):
        user = self.security_staff[0]

        # check with no frequency set
        response = self.client.get(
            reverse('emailpreferences-list'),
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'frequency': EMAIL_FREQUENCY.NEVER})

        # check with daily frequency set
        EmailNotificationPreferences.objects.create(
            user=user, frequency=EMAIL_FREQUENCY.DAILY
        )
        response = self.client.get(
            reverse('emailpreferences-list'),
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'frequency': EMAIL_FREQUENCY.DAILY})
