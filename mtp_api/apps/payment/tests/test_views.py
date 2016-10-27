from datetime import date, timedelta

from django.core.urlresolvers import reverse
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.models import Batch, Payment
from payment.constants import PAYMENT_STATUS
from prison.tests.utils import load_random_prisoner_locations
from payment.tests.utils import generate_payments


class GetBatchViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        _, _, self.bank_admins, _, _, _ = make_test_users()

    def test_get_batch(self):
        user = self.bank_admins[0]

        batch = Batch(date=date(2016, 3, 3))
        batch.save()

        other_batch = Batch(date=date(2016, 3, 4))
        other_batch.save()

        response = self.client.get(
            reverse('batch-list'), {'date': date(2016, 3, 3)}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        batches = response.data['results']
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]['id'], batch.id)
        self.assertEqual(batches[0]['date'], batch.date.isoformat())


class CreatePaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, self.send_money_users, _ = make_test_users()
        load_random_prisoner_locations(2)

    def test_permissions_required(self):
        user = self.prison_clerks[0]

        new_payment = {
            'prisoner_number': 'A1409AE',
            'prisoner_dob': date(1989, 1, 21),
            'recipient_name': 'James Halls',
            'amount': 1000,
            'service_charge': 24,
        }

        response = self.client.post(
            reverse('payment-list'), data=new_payment, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_create(self):
        user = self.send_money_users[0]

        new_payment = {
            'prisoner_number': 'A1409AE',
            'prisoner_dob': date(1989, 1, 21),
            'recipient_name': 'James Halls',
            'amount': 1000,
            'service_charge': 24,
            'email': 'sender@outside.local'
        }

        response = self.client.post(
            reverse('payment-list'), data=new_payment, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        expected_credit = {
            'amount': new_payment['amount'],
            'prisoner_number': new_payment.pop('prisoner_number'),
            'prisoner_dob': new_payment.pop('prisoner_dob'),
        }
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(
            Payment.objects.filter(**new_payment).count(), 1
        )
        credit = Payment.objects.get(**new_payment).credit
        self.assertEqual(credit.amount, expected_credit['amount'])
        self.assertEqual(credit.prisoner_number, expected_credit['prisoner_number'])
        self.assertEqual(credit.prisoner_dob, expected_credit['prisoner_dob'])
        self.assertEqual(credit.resolution, CREDIT_RESOLUTION.INITIAL)
        self.assertIsNotNone(credit.prison)
        self.assertIsNotNone(credit.prisoner_name)
        self.assertEqual(Credit.objects.all().count(), 0)


class UpdatePaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, self.send_money_users, _ = make_test_users()
        load_random_prisoner_locations(2)

    def _test_update_status(self, new_outcome):
        user = self.send_money_users[0]

        new_payment = {
            'prisoner_number': 'A1409AE',
            'prisoner_dob': date(1989, 1, 21),
            'recipient_name': 'James Halls',
            'amount': 1000,
            'service_charge': 24,
            'email': 'sender@outside.local'
        }
        response = self.client.post(
            reverse('payment-list'), data=new_payment, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        payment_uuid = response.data['uuid']

        update = {
            'status': new_outcome
        }

        response = self.client.patch(
            reverse('payment-detail', args=[payment_uuid]),
            data=update, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        return response

    def test_update_status_taken_succeeds(self):
        response = self._test_update_status(PAYMENT_STATUS.TAKEN)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.all()[0].status,
                         PAYMENT_STATUS.TAKEN)
        self.assertEqual(Credit.objects.all()[0].resolution,
                         CREDIT_RESOLUTION.PENDING)
        self.assertIsNotNone(Credit.objects.all()[0].prison)
        self.assertIsNotNone(Credit.objects.all()[0].prisoner_name)
        self.assertIsNotNone(Credit.objects.all()[0].received_at)

    def test_update_status_failed_succeeds(self):
        response = self._test_update_status(PAYMENT_STATUS.FAILED)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.all()[0].status,
                         PAYMENT_STATUS.FAILED)
        self.assertEqual(Payment.objects.all()[0].credit.resolution,
                         CREDIT_RESOLUTION.INITIAL)
        self.assertIsNone(Payment.objects.all()[0].credit.received_at)
        self.assertEqual(Credit.objects.all().count(), 0)

    def test_update_status_failed_after_taken_fails(self):
        first_response = self._test_update_status(PAYMENT_STATUS.TAKEN)
        p_uuid = first_response.data['uuid']

        user = self.send_money_users[0]
        update = {
            'status': PAYMENT_STATUS.FAILED
        }

        response = self.client.patch(
            reverse('payment-detail', args=[p_uuid]),
            data=update, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, http_status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            {'errors': ['Payment cannot be updated in status "taken"']}
        )

        # check no changes in db
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.all()[0].status,
                         PAYMENT_STATUS.TAKEN)
        self.assertEqual(Credit.objects.all()[0].resolution,
                         CREDIT_RESOLUTION.PENDING)


class GetPaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, self.send_money_users, _ = make_test_users()
        load_random_prisoner_locations(2)

    def test_get_payment(self):
        user = self.send_money_users[0]

        new_payment = {
            'prisoner_number': 'A1409AE',
            'prisoner_dob': date(1989, 1, 21),
            'recipient_name': 'James Halls',
            'amount': 1000,
            'service_charge': 24,
            'email': 'sender@outside.local'
        }
        response = self.client.post(
            reverse('payment-list'), data=new_payment, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        payment_uuid = response.data['uuid']

        response = self.client.get(
            reverse('payment-detail', kwargs={'pk': payment_uuid}), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        retrieved_payment = response.data
        self.assertEqual(payment_uuid, retrieved_payment['uuid'])
        self.assertEqual(new_payment['prisoner_number'],
                         retrieved_payment['prisoner_number'])
        self.assertEqual(new_payment['prisoner_dob'].isoformat(),
                         retrieved_payment['prisoner_dob'])


class ListPaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, self.send_money_users, _ = make_test_users()
        load_random_prisoner_locations(50)
        generate_payments(50, days_of_history=1)

    def test_list_payments(self):
        user = self.send_money_users[0]

        five_hours_ago = timezone.now() - timedelta(hours=5)

        response = self.client.get(
            reverse('payment-list'), {'modified__lt': five_hours_ago.isoformat()},
            format='json', HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        retrieved_payments = response.data['results']

        self.assertEqual(
            len(retrieved_payments),
            Payment.objects.filter(
                status=PAYMENT_STATUS.PENDING, modified__lt=five_hours_ago
            ).count()
        )

        for payment in retrieved_payments:
            Payment.objects.get(pk=payment['uuid'], status=PAYMENT_STATUS.PENDING)
