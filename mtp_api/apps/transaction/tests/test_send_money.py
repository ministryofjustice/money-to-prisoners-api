from datetime import date

from django.utils import timezone
from django.core.urlresolvers import reverse
from rest_framework import status as http_status

from transaction.models import Transaction, Log
from transaction.constants import (
    LOG_ACTIONS, TRANSACTION_CATEGORY, PAYMENT_OUTCOME
)
from .test_base import (
    BaseTransactionViewTestCase,
    TransactionRejectsRequestsWithoutPermissionTestMixin
)


class CreateTransactionTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):

    ENDPOINT_VERB = 'post'

    def setUp(self):
        super().setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_authorised_user(self):
        return self.send_money_users[0]

    def _get_url(self, *args, **kwargs):
        return reverse('send_money:transaction-list')

    def test_create(self):
        url = self._get_url()
        user = self._get_authorised_user()

        new_transaction = {
            'prisoner_number': 'A1234BY',
            'prisoner_dob': date(1986, 12, 9),
            'reference': 'Alan Smith',
            'amount': 1000,
            'received_at': timezone.now().replace(microsecond=0),
            'category': TRANSACTION_CATEGORY.ONLINE_CREDIT,
            'payment_outcome': PAYMENT_OUTCOME.PENDING
        }

        response = self.client.post(
            url, data=new_transaction, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)
        self.assertTrue(response.data['id'] > 0)

        # check changes in db
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(
            Transaction.objects.filter(**new_transaction).count(), 1
        )

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=user,
                action=LOG_ACTIONS.CREATED,
                transaction__id__in=Transaction.objects.all().values_list('id', flat=True)
            ).count(),
            1
        )


class UpdateTransactionTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):

    ENDPOINT_VERB = 'post'

    def setUp(self):
        super().setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_authorised_user(self):
        return self.send_money_users[0]

    def _get_url(self, *args, **kwargs):
        return reverse('send_money:transaction-list')

    def _test_update_payment_outcome(self, new_outcome):
        user = self._get_authorised_user()

        transaction = {
            'prisoner_number': 'A1234BY',
            'prisoner_dob': date(1986, 12, 9),
            'reference': 'Alan Smith',
            'amount': 1000,
            'received_at': timezone.now().replace(microsecond=0),
            'category': TRANSACTION_CATEGORY.ONLINE_CREDIT,
            'payment_outcome': PAYMENT_OUTCOME.PENDING
        }
        t_id = Transaction.objects.create(**transaction).id

        update = {
            'payment_outcome': new_outcome
        }

        response = self.client.patch(
            reverse('send_money:transaction-detail', args=[t_id]),
            data=update, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        return response

    def test_update_payment_outcome_taken_succeeds(self):
        response = self._test_update_payment_outcome(PAYMENT_OUTCOME.TAKEN)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['id'] > 0)

        # check changes in db
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(Transaction.objects.all()[0].payment_outcome,
                         PAYMENT_OUTCOME.TAKEN)

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=self._get_authorised_user(),
                action=LOG_ACTIONS.PAYMENT_TAKEN,
                transaction__id__in=Transaction.objects.all().values_list(
                    'id', flat=True)
            ).count(),
            1
        )

    def test_update_payment_outcome_failed_succeeds(self):
        response = self._test_update_payment_outcome(PAYMENT_OUTCOME.FAILED)

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        self.assertTrue(response.data['id'] > 0)

        # check changes in db
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(Transaction.objects.all()[0].payment_outcome,
                         PAYMENT_OUTCOME.FAILED)

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=self._get_authorised_user(),
                action=LOG_ACTIONS.PAYMENT_FAILED,
                transaction__id__in=Transaction.objects.all().values_list(
                    'id', flat=True)
            ).count(),
            1
        )

    def test_update_payment_outcome_failed_after_taken_fails(self):
        first_response = self._test_update_payment_outcome(PAYMENT_OUTCOME.TAKEN)
        t_id = first_response.data['id']

        user = self._get_authorised_user()
        update = {
            'payment_outcome': PAYMENT_OUTCOME.FAILED
        }

        response = self.client.patch(
            reverse('send_money:transaction-detail', args=[t_id]),
            data=update, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, http_status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            {'errors': ['"payment_outcome" cannot be updated from taken to failed']}
        )

        # check no changes in db
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(Transaction.objects.all()[0].payment_outcome,
                         PAYMENT_OUTCOME.TAKEN)

        # check no logs written
        self.assertEqual(
            Log.objects.filter(
                user=self._get_authorised_user(),
                action=LOG_ACTIONS.PAYMENT_FAILED,
                transaction__id__in=Transaction.objects.all().values_list(
                    'id', flat=True)
            ).count(),
            0
        )
