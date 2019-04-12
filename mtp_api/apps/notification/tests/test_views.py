from datetime import timedelta

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from notification.constants import EMAIL_FREQUENCY
from notification.models import Event, EmailNotificationPreferences
from notification.rules import RULES
from core.tests.utils import make_test_users
from credit.models import Credit
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from transaction.tests.utils import generate_transactions


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
        self.assertEqual(response.data['count'], len(RULES))


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
                RULES['HA'].create_event(credit)
        for disbursement in Disbursement.objects.filter(resolution=DISBURSEMENT_RESOLUTION.SENT):
            if RULES['HA'].triggered(disbursement):
                RULES['HA'].create_event(disbursement)

        response = self.client.get(
            reverse('event-list'), format='json',
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

    def test_get_events_filtered_by_date(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        user = self.security_staff[0]

        for credit in Credit.objects.all():
            if RULES['HA'].triggered(credit):
                RULES['HA'].create_event(credit)
        for disbursement in Disbursement.objects.filter(resolution=DISBURSEMENT_RESOLUTION.SENT):
            if RULES['HA'].triggered(disbursement):
                RULES['HA'].create_event(disbursement)

        lt = timezone.now()
        gte = lt - timedelta(days=2)
        response = self.client.get(
            reverse('event-list'),
            {'triggered_at__lt': lt, 'triggered_at__gte': gte},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        self.assertEqual(
            response.data['count'],
            Event.objects.filter(triggered_at__gte=gte, triggered_at__lt=lt).count()
        )

    def test_get_events_filtered_by_trigger(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        user = self.security_staff[0]

        for credit in Credit.objects.all():
            if RULES['HA'].triggered(credit):
                RULES['HA'].create_event(credit)
        for disbursement in Disbursement.objects.filter(resolution=DISBURSEMENT_RESOLUTION.SENT):
            if RULES['HA'].triggered(disbursement):
                RULES['HA'].create_event(disbursement)

        response = self.client.get(
            reverse('event-list'),
            {'for_credit': True},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        for event in response.data['results']:
            self.assertNotEqual(event['credit'], None)

    def test_get_events_grouped_by_profile(self):
        generate_payments(payment_batch=200, days_of_history=5)
        call_command('update_security_profiles')
        user = self.security_staff[0]

        response = self.client.get(
            reverse('event-list'),
            {'rule': 'CSFREQ', 'group_by': 'sender_profile'},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        latest = {}
        for event in Event.objects.filter(rule='CSFREQ'):
            profile_id = event.sender_profile_event.sender_profile.id
            if profile_id not in latest:
                latest[profile_id] = event
            else:
                if latest[profile_id].triggered_at < event.triggered_at:
                    latest[profile_id] = event

        latest_ids = [e.id for e in latest.values()]
        self.assertEqual(response.data['count'], len(latest_ids))
        for event in response.data['results']:
            if event['id'] not in latest_ids:
                self.fail()

    def test_get_events_grouped_by_profile_and_filtered(self):
        generate_payments(payment_batch=200, days_of_history=5)
        call_command('update_security_profiles')
        user = self.security_staff[0]

        lt = timezone.now() - timedelta(days=2)
        gte = lt - timedelta(days=3)
        response = self.client.get(
            reverse('event-list'),
            {'rule': 'CSFREQ', 'group_by': 'sender_profile',
             'triggered_at__lt': lt, 'triggered_at__gte': gte},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data['count'], 0)

        latest = {}
        for event in Event.objects.filter(
            rule='CSFREQ', triggered_at__gte=gte, triggered_at__lt=lt
        ):
            profile_id = event.sender_profile_event.sender_profile.id
            if profile_id not in latest:
                latest[profile_id] = event
            else:
                if latest[profile_id].triggered_at < event.triggered_at:
                    latest[profile_id] = event

        latest_ids = [e.id for e in latest.values()]
        self.assertEqual(response.data['count'], len(latest_ids))
        for event in response.data['results']:
            if event['id'] not in latest_ids:
                self.fail()


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
