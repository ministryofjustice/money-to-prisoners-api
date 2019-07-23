import itertools
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from faker import Faker
from model_mommy import mommy
from rest_framework import status
from rest_framework.test import APITestCase

from notification.constants import EMAIL_FREQUENCY
from notification.models import Event, EmailNotificationPreferences, PrisonerProfileEvent, SenderProfileEvent
from notification.rules import RULES, ENABLED_RULE_CODES
from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin
from security.models import PrisonerProfile, SenderProfile, DebitCardSenderDetails

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

    def test_get_events(self):
        user = self.security_staff[0]

        # visible events, not linked to user
        mommy.make(Event, rule='HA')
        mommy.make(Event, rule='NWN')

        # visible events, linked to user
        mommy.make(Event, user=user, rule='MONP')
        mommy.make(Event, user=user, rule='MONS')

        # this event is not seen as it's linked to a different user
        mommy.make(Event, user=self.security_staff[1], rule='MONP')

        response = self.client.get(
            reverse('event-list'), {'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 4)
        self.assertSetEqual(
            set(event['id'] for event in response.data['results']),
            set(Event.objects.exclude(user=self.security_staff[1]).values_list('id', flat=True))
        )

    def test_get_events_filtered_by_rules(self):
        user = self.security_staff[0]

        # visible events, not linked to user
        mommy.make(Event, rule='HA')
        mommy.make(Event, rule='NWN')

        # visible events, linked to user
        mommy.make(Event, user=user, rule='MONP')
        mommy.make(Event, user=user, rule='MONS')

        response = self.client.get(
            reverse('event-list'),
            {'limit': 1000, 'rule': ['HA', 'NWN']},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertSetEqual(set(
            event['rule']
            for event in response.data['results']
        ), {'HA', 'NWN'})

    def test_get_events_filtered_by_date(self):
        user = self.security_staff[0]

        now = timezone.now()
        for days_into_past in range(1, 3):
            triggered_at = now - timedelta(days=days_into_past)

            # visible events, not linked to user
            mommy.make(Event, rule='HA', triggered_at=triggered_at)
            mommy.make(Event, rule='NWN', triggered_at=triggered_at)

            # visible events, linked to user
            mommy.make(Event, user=user, rule='MONP', triggered_at=triggered_at)
            mommy.make(Event, user=user, rule='MONS', triggered_at=triggered_at)

        response = self.client.get(
            reverse('event-list'),
            {
                'triggered_at__lt': now.isoformat(),
                'triggered_at__gte': (now - timedelta(days=2)).isoformat(),
            },
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2 * 4)

        response = self.client.get(
            reverse('event-list'),
            {
                'triggered_at__lt': now.isoformat(),
                'triggered_at__gte': (now - timedelta(days=2)).isoformat(),
                'rule': ['MONP', 'MONS'],
            },
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2 * 2)

    def test_get_prisoner_monitoring_events_for_user(self):
        user = self.security_staff[0]

        prisoner_profile = mommy.make(PrisonerProfile, prisoner_number='A1409AE')
        prisoner_profile.monitoring_users.add(user)

        for _ in range(2):
            event = mommy.make(Event, user=user, rule='MONP')
            mommy.make(PrisonerProfileEvent, event=event, prisoner_profile=prisoner_profile)

        response = self.client.get(
            reverse('event-list'), {'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertTrue(all(
            event['prisoner_profile']['prisoner_number'] == 'A1409AE'
            for event in response.data['results']
        ))

    def test_get_sender_monitoring_events_for_user(self):
        user = self.security_staff[0]

        sender_profile = mommy.make(SenderProfile)
        mommy.make(DebitCardSenderDetails, postcode='SW1H 9AJ', sender=sender_profile)

        for _ in range(2):
            event = mommy.make(Event, user=user, rule='MONS')
            mommy.make(SenderProfileEvent, event=event, sender_profile=sender_profile)

        response = self.client.get(
            reverse('event-list'), {'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertTrue(all(
            event['sender_profile']['debit_card_details'][0]['postcode'] == 'SW1H 9AJ'
            for event in response.data['results']
        ))


class EmailPreferencesViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.url = reverse('email-preferences')
        test_users = make_test_users()
        self.user = test_users['security_staff'][0]

    def test_turn_on(self):
        response = self.client.post(
            self.url, {'frequency': EMAIL_FREQUENCY.DAILY},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            EmailNotificationPreferences.objects.get(user=self.user).frequency,
            EMAIL_FREQUENCY.DAILY
        )

    def test_turn_off(self):
        EmailNotificationPreferences.objects.create(
            user=self.user, frequency=EMAIL_FREQUENCY.DAILY
        )

        response = self.client.post(
            self.url, {'frequency': EMAIL_FREQUENCY.NEVER},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            EmailNotificationPreferences.objects.get(user=self.user).frequency,
            EMAIL_FREQUENCY.NEVER
        )

    def test_get_frequency(self):
        # check with no frequency set
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'frequency': EMAIL_FREQUENCY.NEVER})

        # check with daily frequency set
        EmailNotificationPreferences.objects.create(
            user=self.user, frequency=EMAIL_FREQUENCY.DAILY
        )
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'frequency': EMAIL_FREQUENCY.DAILY})

    def test_last_sent_maintained_if_turned_on_and_off(self):
        # turn on emails
        response = self.client.post(
            self.url, {'frequency': EMAIL_FREQUENCY.DAILY},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        preference = EmailNotificationPreferences.objects.get(user=self.user)
        self.assertIsNone(preference.last_sent_at)

        # pretend email was sent
        today = timezone.now().date()
        preference.last_sent_at = today
        preference.save()

        # turn off emails and ensure last sent datetime was maintained
        response = self.client.post(
            self.url, {'frequency': EMAIL_FREQUENCY.NEVER},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        preference = EmailNotificationPreferences.objects.get(user=self.user)
        self.assertEqual(preference.last_sent_at, today)

        # turn on emails and ensure last sent datetime was maintained
        response = self.client.post(
            self.url, {'frequency': EMAIL_FREQUENCY.DAILY},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        preference = EmailNotificationPreferences.objects.get(user=self.user)
        self.assertEqual(preference.last_sent_at, today)

    def test_invalid_frequency(self):
        response = self.client.post(
            self.url, {'frequency': ''},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(
            self.url, {'frequency': 'yearly'},
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(EmailNotificationPreferences.objects.exists())
