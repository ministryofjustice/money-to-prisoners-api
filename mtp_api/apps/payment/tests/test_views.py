from datetime import datetime, date, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse, reverse_lazy
from django.test import TestCase
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from credit.constants import CREDIT_RESOLUTION, LOG_ACTIONS
from credit.models import Credit, Log
from mtp_auth.tests.utils import AuthTestCaseMixin
from payment.models import Batch, BillingAddress, Payment
from payment.constants import PAYMENT_STATUS
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from security.models import CHECK_STATUS

User = get_user_model()


class GetBatchViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.bank_admins = make_test_users()['bank_admins']
        load_random_prisoner_locations(2)

    def test_get_batch(self):
        user = self.bank_admins[0]

        batch = Batch(date=date(2016, 3, 3))
        batch.save()

        other_batch = Batch(date=date(2016, 3, 4))
        other_batch.save()

        for i, payment in enumerate(generate_payments(50, days_of_history=1)):
            if i % 2:
                payment.batch = batch
            else:
                payment.batch = other_batch
            payment.save()

        response = self.client.get(
            reverse('batch-list'), {'date': date(2016, 3, 3)}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        batches = response.data['results']
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]['id'], batch.id)
        self.assertEqual(batches[0]['date'], batch.date.isoformat())
        self.assertEqual(batches[0]['payment_amount'], batch.payment_amount)


class CreatePaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.send_money_users = test_users['send_money_users']
        load_random_prisoner_locations(2)

    def test_permissions_required(self):
        user = self.prison_clerks[0]

        new_payment = {
            'prisoner_number': 'A1409AE',
            'prisoner_dob': date(1989, 1, 21),
            'recipient_name': 'James Halls',
            'amount': 1000,
            'service_charge': 24,
            'email': 'sender@outside.local',
            'ip_address': '151.101.16.144',
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
            'email': 'sender@outside.local',
            'ip_address': '151.101.16.144',
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
        payment = Payment.objects.get(**new_payment)
        self.assertEqual(payment.recipient_name, new_payment['recipient_name'])
        self.assertEqual(payment.ip_address, new_payment['ip_address'])
        credit = payment.credit
        self.assertEqual(credit.amount, expected_credit['amount'])
        self.assertEqual(credit.prisoner_number, expected_credit['prisoner_number'])
        self.assertEqual(credit.prisoner_dob, expected_credit['prisoner_dob'])
        self.assertEqual(credit.resolution, CREDIT_RESOLUTION.INITIAL)
        self.assertIsNotNone(credit.prison)
        self.assertIsNotNone(credit.prisoner_name)
        self.assertEqual(Credit.objects.all().count(), 0)

    def test_create_with_missing_ip_address(self):
        user = self.send_money_users[0]
        new_payment = {
            'prisoner_number': 'A1409AE',
            'prisoner_dob': date(1989, 1, 21),
            'recipient_name': 'James Halls',
            'amount': 1000,
            'service_charge': 24,
            'email': 'sender@outside.local',
        }
        response = self.client.post(
            reverse('payment-list'), data=new_payment, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED,
                         'Should allow payment creation without IP address')
        self.assertTrue(response.data['uuid'] is not None)

        new_payment['ip_address'] = None
        response = self.client.post(
            reverse('payment-list'), data=new_payment, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED,
                         'Should allow payment creation with unknown IP address')
        self.assertTrue(response.data['uuid'] is not None)


class UpdatePaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.send_money_users = test_users['send_money_users']
        load_random_prisoner_locations(2)

    def _test_update_payment(self, **update_fields):
        self.user = self.send_money_users[0]

        new_payment = {
            'prisoner_number': 'A1409AE',
            'prisoner_dob': date(1989, 1, 21),
            'recipient_name': 'James Halls',
            'amount': 1000,
            'service_charge': 24,
            'email': 'sender@outside.local',
            'ip_address': '151.101.16.144',
        }
        response = self.client.post(
            reverse('payment-list'),
            data=new_payment,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user),
        )
        self.payment_uuid = response.data['uuid']

        response = self.client.patch(
            reverse('payment-detail', args=[self.payment_uuid]),
            data=update_fields,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user),
        )
        return response

    def test_update_status_to_taken_succeeds(self):
        response = self._test_update_payment(status=PAYMENT_STATUS.TAKEN)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)

        payment = Payment.objects.first()
        credit = payment.credit

        self.assertEqual(payment.status, PAYMENT_STATUS.TAKEN)
        self.assertEqual(credit.resolution, CREDIT_RESOLUTION.PENDING)
        self.assertIsNotNone(credit.prison)
        self.assertIsNotNone(credit.prisoner_name)
        self.assertIsNotNone(credit.received_at)

    def test_update_status_to_rejected_succeeds(self):
        # First update, that generates a check
        self._test_update_payment(**{
            'email': 'someone@mtp.local',
            'cardholder_name': 'Mr Testy McTestington',
            'card_number_first_digits': '1234',
            'card_number_last_digits': '9876',
            'card_expiry_date': '10/30',
            'billing_address': {
                'line1': '62 Petty France',
                'line2': '',
                'city': 'London',
                'country': 'UK',
                'postcode': 'SW1H 9EU'
            }
        })
        payment = Payment.objects.first()
        credit = payment.credit
        self.assertQuerysetEqual(credit.prisoner_profile.senders.all(), [credit.sender_profile], transform=lambda x: x)
        self.assertQuerysetEqual(credit.sender_profile.prisons.all(), [credit.prison], transform=lambda x: x)

        response = self.client.patch(
            reverse('payment-detail', args=[self.payment_uuid]),
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.user),
            data=dict(status=PAYMENT_STATUS.REJECTED)
        )
        payment.refresh_from_db()
        # We cannot refresh_from_db because we override the default Manager to exclude the state we're mutating into :(
        credit = Credit.objects_all.get(id=credit.id)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)

        self.assertEqual(payment.status, PAYMENT_STATUS.REJECTED)
        self.assertEqual(credit.resolution, CREDIT_RESOLUTION.FAILED)
        self.assertQuerysetEqual(credit.prisoner_profile.senders.all(), [])
        self.assertQuerysetEqual(credit.sender_profile.prisons.all(), [])
        self.assertIsNotNone(credit.prison)
        self.assertIsNotNone(credit.prisoner_name)
        self.assertIsNone(credit.received_at)

        self.assertEqual(Log.objects.count(), 1)
        log = Log.objects.first()
        self.assertEqual(log.action, LOG_ACTIONS.FAILED)

    def test_update_status_to_expired_succeeds(self):
        response = self._test_update_payment(status=PAYMENT_STATUS.EXPIRED)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)

        payment = Payment.objects.first()
        credit = payment.credit

        self.assertEqual(payment.status, PAYMENT_STATUS.EXPIRED)
        self.assertEqual(credit.resolution, CREDIT_RESOLUTION.FAILED)
        self.assertIsNotNone(credit.prison)
        self.assertIsNotNone(credit.prisoner_name)
        self.assertIsNone(credit.received_at)

        self.assertEqual(Log.objects.count(), 1)
        log = Log.objects.first()
        self.assertEqual(log.action, LOG_ACTIONS.FAILED)

    def test_update_received_at_succeeds(self):
        received_at = datetime(2016, 9, 22, 23, 12, tzinfo=timezone.utc)
        response = self._test_update_payment(
            status=PAYMENT_STATUS.TAKEN, received_at=received_at.isoformat()
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)

        payment = Payment.objects.first()
        credit = payment.credit

        self.assertEqual(payment.status, PAYMENT_STATUS.TAKEN)
        self.assertEqual(credit.resolution, CREDIT_RESOLUTION.PENDING)
        self.assertIsNotNone(credit.prison)
        self.assertIsNotNone(credit.prisoner_name)
        self.assertEqual(credit.received_at, received_at)

    def test_update_status_to_failed_succeeds(self):
        response = self._test_update_payment(status=PAYMENT_STATUS.FAILED)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)

        payment = Payment.objects.first()
        credit = payment.credit

        self.assertEqual(payment.status, PAYMENT_STATUS.FAILED)
        self.assertEqual(credit.resolution, CREDIT_RESOLUTION.INITIAL)
        self.assertIsNone(credit.received_at)
        self.assertEqual(Credit.objects.count(), 0)

    def test_update_status_to_failed_after_taken_fails(self):
        first_response = self._test_update_payment(status=PAYMENT_STATUS.TAKEN)
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

        payment = Payment.objects.first()
        credit = payment.credit

        self.assertEqual(payment.status, PAYMENT_STATUS.TAKEN)
        self.assertEqual(credit.resolution, CREDIT_RESOLUTION.PENDING)

    def test_update_with_billing_address(self):
        billing_address = {
            'line1': '62 Petty France',
            'line2': '',
            'city': 'London',
            'country': 'UK',
            'postcode': 'SW1H 9EU'
        }
        response = self._test_update_payment(
            status=PAYMENT_STATUS.TAKEN,
            billing_address=billing_address
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)
        payment = Payment.objects.all()[0]
        self.assertEqual(payment.status, PAYMENT_STATUS.TAKEN)
        self.assertIsNotNone(payment.billing_address)
        self.assertEqual(payment.billing_address.line1, billing_address['line1'])
        self.assertEqual(payment.billing_address.postcode, billing_address['postcode'])

    def test_update_fails_with_bad_billing_address(self):
        bad_billing_address = 45
        response = self._test_update_payment(
            status=PAYMENT_STATUS.TAKEN,
            billing_address=bad_billing_address
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)
        payment = Payment.objects.all()[0]
        self.assertEqual(payment.status, PAYMENT_STATUS.PENDING)
        self.assertIsNone(payment.billing_address)

    def test_update_with_billing_address_twice_updates_in_place(self):
        billing_address_1 = {
            'line1': '62 Petty France',
            'line2': '',
            'city': 'London',
            'country': 'UK',
            'postcode': 'SW1H 9EU'
        }
        response = self._test_update_payment(
            billing_address=billing_address_1
        )

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['uuid'] is not None)

        # check changes in db
        self.assertEqual(Payment.objects.count(), 1)
        payment = Payment.objects.all()[0]
        self.assertIsNotNone(payment.billing_address)
        self.assertEqual(payment.billing_address.line1, billing_address_1['line1'])

        billing_address_2 = {
            'line1': '70 Petty France',
            'line2': '',
            'city': 'London',
            'country': 'UK',
            'postcode': 'SW1H 9EU'
        }
        response = self.client.patch(
            reverse('payment-detail', args=[response.data['uuid']]),
            data={'billing_address': billing_address_2}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_users[0])
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        # check no additional billing address created
        self.assertEqual(BillingAddress.objects.count(), 1)
        self.assertEqual(
            Payment.objects.all()[0].billing_address,
            BillingAddress.objects.all()[0]
        )
        # check billing address has been updated
        self.assertEqual(
            BillingAddress.objects.all()[0].line1,
            billing_address_2['line1']
        )


class GetPaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_fiu_user = test_users['security_fiu_users'][0]
        self.send_money_user = test_users['send_money_users'][0]
        load_random_prisoner_locations(2)

    def _start_new_payment(self):
        # this starts a new payment; the sender has not yet provided their card details
        new_payment = {
            'prisoner_number': 'A1409AE',
            'prisoner_dob': date(1989, 1, 21),
            'recipient_name': 'James Halls',
            'amount': 1000,
            'service_charge': 24,
        }
        response = self.client.post(
            reverse('payment-list'), data=new_payment, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user)
        )
        new_payment['uuid'] = response.data['uuid']
        return new_payment

    def test_get_details_of_new_payment(self):
        new_payment = self._start_new_payment()
        response = self.client.get(
            reverse('payment-detail', kwargs={'pk': new_payment['uuid']}), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user)
        )
        retrieved_payment = response.data
        self.assertEqual(new_payment['uuid'], retrieved_payment['uuid'])
        self.assertEqual(new_payment['prisoner_number'], retrieved_payment['prisoner_number'])
        self.assertEqual(new_payment['prisoner_dob'].isoformat(), retrieved_payment['prisoner_dob'])
        self.assertIsNone(retrieved_payment['security_check'])

    def _complete_new_payment(self, payment_uuid):
        # this completes the payment from the sender's side; the payment is not yet captured
        payment_update = {
            'email': 'sender@outside.local',
            'ip_address': '151.101.16.144',
            'worldpay_id': '12345678',
            'cardholder_name': 'Mary Halls',
            'card_number_first_digits': '111111',
            'card_number_last_digits': '2222',
            'card_expiry_date': '01/20',
            'card_brand': 'Brand',
            'billing_address': {
                'line1': '62 Petty France',
                'city': 'London',
                'postcode': 'SW1H 9EU',
                'country': 'UK',
            },
        }
        response = self.client.patch(
            reverse('payment-detail', kwargs={'pk': payment_uuid}), data=payment_update, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user)
        )
        retrieved_payment = response.data
        self.assertEqual(payment_update['email'], retrieved_payment['email'])
        self.assertEqual(payment_update['ip_address'], retrieved_payment['ip_address'])

    def test_get_security_check_details_of_completed_payment(self):
        new_payment = self._start_new_payment()
        payment = Payment.objects.get(pk=new_payment['uuid'])
        self._complete_new_payment(new_payment['uuid'])
        response = self.client.get(
            reverse('payment-detail', kwargs={'pk': new_payment['uuid']}), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user)
        )
        retrieved_payment = response.data
        security_check = retrieved_payment['security_check']
        self.assertEqual(security_check['status'], CHECK_STATUS.ACCEPTED)
        self.assertEqual(security_check['user_actioned'], False)

        # reset check to pending
        check = payment.credit.security_check
        check.status = CHECK_STATUS.PENDING
        check.description = 'Credit matched FIU monitoring rules'
        check.rules = ['FIUMONP']
        check.save()
        response = self.client.get(
            reverse('payment-detail', kwargs={'pk': new_payment['uuid']}), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user)
        )
        retrieved_payment = response.data
        security_check = retrieved_payment['security_check']
        self.assertEqual(security_check['status'], CHECK_STATUS.PENDING)
        self.assertEqual(security_check['user_actioned'], False)

        # mock rejected check
        check.reject(self.security_fiu_user, 'Cap exceeded')
        response = self.client.get(
            reverse('payment-detail', kwargs={'pk': new_payment['uuid']}), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user)
        )
        retrieved_payment = response.data
        security_check = retrieved_payment['security_check']
        self.assertEqual(security_check['status'], CHECK_STATUS.REJECTED)
        self.assertEqual(security_check['user_actioned'], True)


class ListPaymentViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.send_money_users = test_users['send_money_users']
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


class PaymentSearchAdminView(TestCase):
    url = reverse_lazy('admin:payment_search')

    def assertCannotAccessPaymentSearch(self, msg):  # noqa: N802
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302, msg=msg)

    def test_access_denied_to_admins(self):
        self.assertCannotAccessPaymentSearch('Should not be able to access without login')

        User.objects.create_user('user', 'user@mtp.local', 'user')
        self.assertTrue(self.client.login(
            username='user',
            password='user',
        ))
        self.assertCannotAccessPaymentSearch('Should not be able to access as a non-staff')
        self.client.logout()

        User.objects.create_user('staffuser', 'staffuser@mtp.local', 'staffuser')
        self.assertTrue(self.client.login(
            username='staffuser',
            password='staffuser',
            is_staff=True,
        ))
        self.assertCannotAccessPaymentSearch('Should not be able to access as a plain staff user')
        self.client.logout()

    def test_accessible_by_superusers(self):
        User.objects.create_superuser('superuser', 'superuser@mtp.local', 'superuser')
        self.assertTrue(self.client.login(
            username='superuser',
            password='superuser',
        ))
        response = self.client.get(self.url)
        self.assertContains(response, 'Payment search')
