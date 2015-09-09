import json

from django.core.urlresolvers import reverse
from rest_framework import status as http_status

from transaction.models import Transaction, Log
from transaction.constants import TRANSACTION_STATUS, LOG_ACTIONS
from transaction.api.bank_admin.views import TransactionView
from transaction.api.bank_admin.serializers import CreateTransactionSerializer, \
    UpdateRefundedTransactionSerializer

from .utils import generate_transactions_data, generate_transactions
from .test_base import BaseTransactionViewTestCase, \
    TransactionRejectsRequestsWithoutPermissionTestMixin


class CreateTransactionsTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):
    ENDPOINT_VERB = 'post'

    def setUp(self):
        super(CreateTransactionsTestCase, self).setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_authorised_user(self):
        return self.bank_admins[0]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-list')

    def _get_transactions_data(self, tot=30):
        data_list = generate_transactions_data(
            transaction_batch=tot,
            status=TRANSACTION_STATUS.AVAILABLE
        )

        serializer = CreateTransactionSerializer()
        keys = serializer.get_fields().keys()

        return [
            {k: data[k] for k in keys if k in data}
            for data in data_list
        ]

    def test_create_list(self):
        """
        POST on transactions endpoint should create list of transactions.
        """

        url = self._get_url()
        data_list = self._get_transactions_data()

        user = self.bank_admins[0]

        response = self.client.post(
            url, data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        # check changes in db
        self.assertEqual(len(data_list), Transaction.objects.count())
        for data in data_list:
            self.assertEqual(
                Transaction.objects.filter(**data).count(), 1
            )

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=user,
                action=LOG_ACTIONS.CREATED,
                transaction__id__in=Transaction.objects.all().values_list('id', flat=True)
            ).count(),
            len(data_list)
        )

    def _create_list_with_null_field(self, null_field):
        url = self._get_url()
        data_list = self._get_transactions_data()

        user = self.bank_admins[0]
        data_list[0][null_field] = None

        return self.client.post(
            url, data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

    def test_create_list_null_account_number_fails(self):
        current_count = Transaction.objects.count()

        response = self._create_list_with_null_field('sender_account_number')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # check no change in db
        self.assertEqual(current_count, Transaction.objects.count())

    def test_create_list_null_sort_code_fails(self):
        current_count = Transaction.objects.count()

        response = self._create_list_with_null_field('sender_sort_code')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # check no change in db
        self.assertEqual(current_count, Transaction.objects.count())

    def test_create_list_null_amount_fails(self):
        current_count = Transaction.objects.count()

        response = self._create_list_with_null_field('amount')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # check no change in db
        self.assertEqual(current_count, Transaction.objects.count())


class UpdateTransactionsTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):

    ENDPOINT_VERB = 'patch'

    def setUp(self):
        super(UpdateTransactionsTestCase, self).setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_unauthorised_user(self):
        return self.bank_admins[0]

    def _get_authorised_user(self):
        return self.refund_bank_admins[0]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-patch-refunded')

    def _get_transactions(self, tot=30):
        transactions = generate_transactions(transaction_batch=tot)

        data_list = []
        for i, trans in enumerate(transactions):
            trans.save()
            refund = False
            if not trans.prisoner_number and not trans.refunded:
                refund = True
            data_list.append({'id': trans.id, 'refunded': refund})

        return data_list

    def test_patch_refunded(self):
        """PATCH on endpoint should update refunded status of given transactions"""

        url = self._get_url()
        data_list = self._get_transactions()

        user = self._get_authorised_user()

        response = self.client.patch(
            url, data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        # check changes in db
        for data in data_list:
            if data['refunded']:
                self.assertTrue(Transaction.objects.get(id=data['id']).refunded)

        # check logs
        refunded_data_list = [t['id'] for t in data_list if t['refunded']]
        self.assertEqual(
            Log.objects.filter(
                user=user,
                action=LOG_ACTIONS.REFUNDED,
                transaction__id__in=Transaction.objects.all().values_list('id', flat=True)
            ).count(),
            len(refunded_data_list)
        )

    def _patch_refunded_with_invalid_status(self, valid_data_list, status):
        url = self._get_url()
        user = self._get_authorised_user()

        invalid_transactions = Transaction.objects.filter(
            **Transaction.STATUS_LOOKUP[status])
        invalid_data_list = (
            [{'id': t.id, 'refunded': True} for t in invalid_transactions]
        )

        return self.client.patch(
            url, data=valid_data_list + invalid_data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

    def test_patch_credited_creates_conflict(self):
        valid_data_list = self._get_transactions()
        response = self._patch_refunded_with_invalid_status(
            valid_data_list, 'credited')

        self.assertEqual(response.status_code, http_status.HTTP_409_CONFLICT)

        # check that entire update failed
        for data in valid_data_list:
            if data['refunded']:
                self.assertFalse(
                    Transaction.objects.get(id=data['id']).refunded
                )

    def test_patch_refunded_creates_conflict(self):
        valid_data_list = self._get_transactions()
        response = self._patch_refunded_with_invalid_status(
            valid_data_list, 'refunded')

        self.assertEqual(response.status_code, http_status.HTTP_409_CONFLICT)

        # check that entire update failed
        for data in valid_data_list:
            if data['refunded']:
                self.assertFalse(
                    Transaction.objects.get(id=data['id']).refunded
                )

    def test_patch_cannot_update_disallowed_fields(self):
        """ PATCH should not update fields other than refunded """

        url = self._get_url()
        data_list = self._get_transactions()
        for item in data_list:
            item['prisoner_number'] = 'AAAAAAA'

        user = self._get_authorised_user()

        response = self.client.patch(
            url, data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        # check lack changes in db
        for data in data_list:
            self.assertNotEqual(
                Transaction.objects.get(id=data['id']).prisoner_number, data['prisoner_number']
            )


class GetTransactionsAsBankAdminTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):
    ENDPOINT_VERB = 'get'

    def setUp(self):
        super(GetTransactionsAsBankAdminTestCase, self).setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

        data_list = self._populate_transactions()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-list')

    def _populate_transactions(self, tot=10):
        transactions = generate_transactions(transaction_batch=tot)

        for i, trans in enumerate(transactions):
            trans.save()

    def _get_with_status(self, user, status_arg):
        url = self._get_url()

        response = self.client.get(
            url, {'status': status_arg, 'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        return response.data

    def _test_get_list_with_status(self, status_str_arg, statuses):
        data = self._get_with_status(self._get_authorised_user(),
                                     status_str_arg)

        # check that all matching db records are returned
        db_ids = []
        for status in statuses:
            ts = list(Transaction.objects.filter(
                **Transaction.STATUS_LOOKUP[status]))
            db_ids += [t.id for t in ts]
        self.assertEqual(len(set(db_ids)), len(data['results']))

        # check that all results match one of the provided statuses
        for t in data['results']:
            matches_one = False
            for status in statuses:
                try:
                    trans = Transaction.objects.get(
                        id=t['id'],
                        **Transaction.STATUS_LOOKUP[status])
                    matches_one = True
                    break
                except Transaction.DoesNotExist:
                    pass
            self.assertTrue(matches_one)

        return data['results']

    def _get_authorised_user(self):
        return self.bank_admins[0]

    def _assert_required_fields_present(self, results):
        for t in results:
            self.assertTrue('prison' in t and
                            'amount' in t and
                            'credited' in t and
                            'refunded' in t)
            if t['prison'] is not None:
                self.assertTrue('nomis_id' in t['prison'] and
                                'name' in t['prison'])

    def _assert_hidden_fields_absent(self, results):
        for t in results:
            self.assertTrue('sender_account_number' not in t and
                            'sender_sort_code' not in t and
                            'sender_roll_number' not in t and
                            'sender_name' not in t)

    def _test_get_list_with_status_verify_fields(
        self, status_str_arg, statuses
    ):
        results = self._test_get_list_with_status(status_str_arg, statuses)
        self._assert_required_fields_present(results)
        self._assert_hidden_fields_absent(results)

    def test_get_list_all(self):
        results = self._test_get_list_with_status_verify_fields(
            '',
            TRANSACTION_STATUS.values.keys())

    def test_get_list_refund_pending(self):
        results = self._test_get_list_with_status_verify_fields(
            'refund_pending',
            ['refund_pending'])

    def test_get_list_credit_refunded(self):
        results = self._test_get_list_with_status_verify_fields(
            'credited,refunded',
            ['credited', 'refunded'])

    def test_get_list_credit_refunded_refund_pending(self):
        results = self._test_get_list_with_status_verify_fields(
            'credited,refunded,refund_pending',
            ['credited', 'refunded', 'refund_pending'])

    def test_get_list_invalid_status_bad_request(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.get(
            url, {'status': 'not_a_real_status'}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)


class GetTransactionsAsRefundBankAdminTestCase(GetTransactionsAsBankAdminTestCase):

    def _get_authorised_user(self):
        return self.refund_bank_admins[0]

    def _assert_required_fields_present(self, results):
        for t in results:
            self.assertTrue('sender_account_number' in t and
                            'sender_sort_code' in t and
                            'sender_name' in t and
                            'amount' in t)

    def _assert_hidden_fields_absent(self, results):
        pass
