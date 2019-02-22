from datetime import timedelta

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from notification.constants import EMAIL_FREQUENCY
from notification.models import (
    Subscription, Parameter, Event, EmailNotificationPreferences
)
from notification.rules import RULES
from core.tests.utils import make_test_users
from credit.models import Credit
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.constants import TIME_PERIOD
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


class ListSubscriptionViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']

    def test_get_subscriptions(self):
        user = self.security_staff[0]

        # viewable subscription
        subscription1 = Subscription.objects.create(
            rule='VOX', user=user
        )
        subscription1.parameters.add(
            Parameter(field='amount__gte', value=100), bulk=False
        )

        # someone elses's (non-viewable) subscription
        subscription2 = Subscription.objects.create(
            rule='CSFREQ', user=self.security_staff[1]
        )
        subscription2.parameters.add(
            Parameter(field='amount__gte', value=150), bulk=False
        )

        response = self.client.get(
            reverse('subscription-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], subscription1.id)


class CreateSubscriptionViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']

    def test_create_subscription(self):
        user = self.security_staff[0]

        new_subscription = {
            'rule': 'VOX',
            'parameters': [
                {'field': 'amount__gte', 'value': 100},
                {'field': 'payment__email', 'value': 'sender@mtp.local'},
            ]
        }

        response = self.client.post(
            reverse('subscription-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
            data=new_subscription
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(
            Subscription.objects.all().count(), 1
        )
        self.assertEqual(
            Subscription.objects.all()[0].rule, 'VOX'
        )
        self.assertEqual(
            Subscription.objects.all()[0].user, user
        )
        self.assertEqual(
            Subscription.objects.all()[0].parameters.all().count(), 2
        )

    def test_cannot_create_subscription_for_invalid_rule(self):
        user = self.security_staff[0]

        new_subscription = {
            'rule': 'FAKE',
            'parameters': [
                {'field': 'amount__gte', 'value': 100},
                {'field': 'payment__email', 'value': 'sender@mtp.local'},
            ]
        }

        response = self.client.post(
            reverse('subscription-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
            data=new_subscription
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(
            Subscription.objects.all().count(), 0
        )


class DeleteSubscriptionViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff']

    def test_delete_subscription(self):
        user = self.security_staff[0]

        subscription = Subscription.objects.create(
            rule='VOX', user=user
        )
        subscription.parameters.add(
            Parameter(field='amount__gte', value=100), bulk=False
        )

        response = self.client.delete(
            reverse('subscription-detail', kwargs={'pk': subscription.pk}),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.assertEqual(
            Subscription.objects.all().count(), 0
        )

    def test_cannot_delete_another_users_subscription(self):
        user = self.security_staff[0]

        subscription = Subscription.objects.create(
            rule='VOX', user=self.security_staff[1]
        )
        subscription.parameters.add(
            Parameter(field='amount__gte', value=100), bulk=False
        )

        response = self.client.delete(
            reverse('subscription-detail', kwargs={'pk': subscription.pk}),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.assertEqual(
            Subscription.objects.all().count(), 1
        )


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

        start = timezone.now() - timedelta(days=2)
        # viewable subscription
        subscription = Subscription.objects.create(
            rule='VOX', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='amount__gte', value=100), bulk=False
        )
        subscription.create_events()

        response = self.client.get(
            reverse('event-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        triggering_credits = Credit.objects.filter(
            amount__gte=100,
        )
        triggering_disbursements = Disbursement.objects.filter(
            amount__gte=100, resolution=DISBURSEMENT_RESOLUTION.SENT
        )
        self.assertEqual(
            response.data['count'],
            triggering_credits.count() + triggering_disbursements.count()
        )

    def test_triggering_credit_ordered_first(self):
        generate_transactions(transaction_batch=200, days_of_history=5)
        generate_payments(payment_batch=200, days_of_history=5)
        call_command('update_security_profiles')
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        # viewable subscription
        subscription = Subscription.objects.create(
            rule='CSFREQ', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='totals__time_period', value=TIME_PERIOD.LAST_7_DAYS),
            Parameter(field='totals__credit_count__gte', value=2),
            bulk=False
        )
        subscription.create_events()

        response = self.client.get(
            reverse('event-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        if response.data['count'] < 2:
            print('Cannot test ordering on lists of less than 2 values')

        for event in response.data['results']:
            first_credit = event['credits'][0]

            db_event = Event.objects.get(
                id=event['id']
            )
            trigger_found = False
            for credit_event in db_event.eventcredit_set.all():
                if credit_event.triggering:
                    self.assertEqual(credit_event.credit.id, first_credit['id'])
                    trigger_found = True

            # check subsequent credits ordered by received_at
            last_date = None
            for credit in event['credits'][1:]:
                if last_date:
                    self.assertGreaterEqual(last_date, credit['received_at'])
                last_date = credit['received_at']

            self.assertTrue(trigger_found)

    def test_get_events_filtered_by_date(self):
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=100, days_of_history=5)
        user = self.security_staff[0]

        start = timezone.now() - timedelta(days=2)
        # viewable subscription
        subscription = Subscription.objects.create(
            rule='VOX', user=user, start=start
        )
        subscription.parameters.add(
            Parameter(field='amount__gte', value=100), bulk=False
        )
        subscription.create_events()

        lt = timezone.now()
        gte = start + timedelta(days=1)
        response = self.client.get(
            reverse('event-list'),
            {'created__lt': lt, 'created__gte': gte},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            response.data['count'],
            Event.objects.filter(created__gte=gte, created__lt=lt).count()
        )


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
