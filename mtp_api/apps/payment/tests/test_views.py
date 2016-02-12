from datetime import date

from django.core.urlresolvers import reverse
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.models import Payment
from payment.constants import PAYMENT_STATUS
from transaction.models import Transaction


class CreatePaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, self.send_money_users = make_test_users()

    def test_permissions_required(self):
        user = self.prison_clerks[0]

        new_payment = {
            'prisoner_number': 'A1234BY',
            'prisoner_dob': date(1986, 12, 9),
            'recipient_name': 'Alan Smith',
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
            'prisoner_number': 'A1234BY',
            'prisoner_dob': date(1986, 12, 9),
            'recipient_name': 'Alan Smith',
            'amount': 1000,
            'service_charge': 24
        }

        response = self.client.post(
            reverse('payment-list'), data=new_payment, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(
            Payment.objects.filter(**new_payment).count(), 1
        )


class UpdatePaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, _, _, self.send_money_users = make_test_users()

    def _test_update_status(self, new_outcome):
        user = self.send_money_users[0]

        new_payment = {
            'prisoner_number': 'A1234BY',
            'prisoner_dob': date(1986, 12, 9),
            'recipient_name': 'Alan Smith',
            'amount': 1000,
            'service_charge': 24
        }
        payment_uuid = Payment.objects.create(**new_payment).uuid

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

        # check transaction has been created
        self.assertEqual(Transaction.objects.count(), 1)
        transaction = Transaction.objects.all()[0]
        self.assertEqual(transaction.id, response.data['transaction'])
        self.assertEqual(transaction.amount, response.data['amount'])
        self.assertEqual(transaction.prisoner_number, response.data['prisoner_number'])
        self.assertEqual(transaction.prisoner_dob.isoformat(), response.data['prisoner_dob'])

    def test_update_status_failed_succeeds(self):
        response = self._test_update_status(PAYMENT_STATUS.FAILED)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Payment.objects.all()[0].status,
                         PAYMENT_STATUS.FAILED)

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
