from datetime import datetime, date, timedelta, time
from unittest import mock

from django.utils import timezone
from django.core.urlresolvers import reverse
from rest_framework import status as http_status

from account.models import Batch
from transaction.models import Transaction, Log
from transaction.constants import TRANSACTION_STATUS, LOG_ACTIONS
from transaction.api.bank_admin.serializers import CreateTransactionSerializer
from .utils import generate_initial_transactions_data, generate_transactions
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
        data_list = generate_initial_transactions_data(tot=tot)

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

    @mock.patch('transaction.api.bank_admin.serializers.transaction_prisons_need_updating')
    def test_create_sends_transaction_prisons_need_updating_signal(
        self, mocked_transaction_prisons_need_updating
    ):
        user = self.bank_admins[0]

        response = self.client.post(
            self._get_url(), data=self._get_transactions_data(), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        mocked_transaction_prisons_need_updating.send.assert_called_with(sender=Transaction)

    def test_create_with_debit_category(self):
        user = self.bank_admins[0]
        data_list = self._get_transactions_data()
        data_list[0]['category'] = 'debit'

        response = self.client.post(
            self._get_url(), data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        self.assertEqual(
            Transaction.objects.filter(**data_list[0]).count(), 1
        )


class UpdateRefundTransactionsTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):

    ENDPOINT_VERB = 'patch'

    def setUp(self):
        super(UpdateRefundTransactionsTestCase, self).setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_unauthorised_user(self):
        return self.prison_clerks[0]

    def _get_authorised_user(self):
        return self.refund_bank_admins[0]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-list')

    def _get_transactions(self, tot=30):
        transactions = generate_transactions(transaction_batch=tot)

        data_list = []
        for i, trans in enumerate(transactions):
            refund = False
            if not trans.prisoner_number and not trans.refunded:
                refund = True
            data_list.append({'id': trans.id, 'refunded': refund})

        return data_list

    def test_patch_refunded(self):
        """PATCH on endpoint should update status of given transactions"""

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

        self._populate_transactions()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-list')

    def _populate_transactions(self, tot=20):
        transactions = generate_transactions(transaction_batch=tot)

    def _get_authorised_user(self):
        return self.bank_admins[0]

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

    def _assert_required_fields_present(self, results):
        for t in results:
            self.assertTrue('prison' in t and
                            'amount' in t and
                            'credited' in t and
                            'refunded' in t)
            if t['prison'] is not None:
                self.assertTrue('nomis_id' in t['prison'] and
                                'general_ledger_code' in t['prison'] and
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


class GetTransactionsRelatedToBatchesTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):
    ENDPOINT_VERB = 'get'

    def setUp(self):
        super(GetTransactionsRelatedToBatchesTestCase, self).setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

        self._populate_transactions()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-list')

    def _populate_transactions(self, tot=40):
        transactions = generate_transactions(transaction_batch=tot)

    def _get_authorised_user(self):
        return self.bank_admins[0]

    def test_get_list_for_batch(self):
        url = self._get_url()
        user = self._get_authorised_user()

        adi_batch = Batch()
        adi_batch.label = 'ADIREFUND'
        adi_batch.save()

        adi_batch.transactions = list(Transaction.objects.filter(
            **Transaction.STATUS_LOOKUP['refunded']))
        adi_batch.save()

        response = self.client.get(
            url, {'batch': adi_batch.id, 'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        results = response.data['results']
        self.assertEqual(len(results), len(adi_batch.transactions.all()))
        for trans in results:
            self.assertTrue(trans['id'] in [t.id for t in adi_batch.transactions.all()])

    def get_list_for_invalid_batch_fails(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.get(
            url, {'batch': 3, 'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_get_list_excluding_label(self):
        """
        Tests that only transactions not attached to a batch of the given type
        will be returned.
        """
        url = self._get_url()
        user = self._get_authorised_user()

        adi_batch = Batch()
        adi_batch.label = 'ADIREFUND'
        adi_batch.save()

        refunded_trans = list(Transaction.objects.filter(
            **Transaction.STATUS_LOOKUP['refunded']))
        attached = [a for (i, a) in enumerate(refunded_trans) if i % 2]
        unattached = [a for (i, a) in enumerate(refunded_trans) if not i % 2]
        self.assertTrue(len(attached) >= 1)
        self.assertTrue(len(unattached) >= 1)

        adi_batch.transactions = attached
        adi_batch.save()

        response = self.client.get(
            url, {'status': 'refunded',
                  'exclude_batch_label': 'ADIREFUND',
                  'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        results = response.data['results']
        self.assertEqual(len(results), len(unattached))

        attached_ids = [t.id for t in attached]
        unattached_ids = [t.id for t in unattached]
        for trans in results:
            self.assertTrue(trans['id'] not in attached_ids)
            self.assertTrue(trans['id'] in unattached_ids)

    def test_get_list_excluding_invalid_label_includes_all(self):
        url = self._get_url()
        user = self._get_authorised_user()

        adi_batch = Batch()
        adi_batch.label = 'ADIREFUND'
        adi_batch.save()

        refunded_trans = list(Transaction.objects.filter(
            **Transaction.STATUS_LOOKUP['refunded']))
        attached = [a for (i, a) in enumerate(refunded_trans) if i % 2]
        self.assertTrue(len(attached) >= 1)

        adi_batch.transactions = attached
        adi_batch.save()

        response = self.client.get(
            url, {'status': 'refunded',
                  'exclude_batch_label': 'WIBBLE',
                  'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        results = response.data['results']
        self.assertEqual(len(results), len(refunded_trans))

        result_ids = [t['id'] for t in results]
        for trans in refunded_trans:
            self.assertTrue(trans.id in result_ids)


class GetTransactionsFilteredByDateTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):
    ENDPOINT_VERB = 'get'

    def setUp(self):
        super().setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

        self._populate_transactions()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-list')

    def _populate_transactions(self, tot=80):
        transactions = generate_transactions(transaction_batch=tot)

    def _get_authorised_user(self):
        return self.bank_admins[0]

    def test_get_list_received_between_dates(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.get(
            url, {'received_at__lt': date.today(),
                  'received_at__gte': date.today() - timedelta(days=2),
                  'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        results = response.data['results']
        result_ids = [t['id'] for t in results]
        today = datetime.combine(date.today(), time.min).replace(
            tzinfo=timezone.get_current_timezone())
        received_between_dates = Transaction.objects.filter(
            received_at__lt=today,
            received_at__gte=(today - timedelta(days=2))
        )
        self.assertEquals(len(result_ids), len(received_between_dates))

        for trans in received_between_dates:
            self.assertTrue(trans.id in result_ids)

class ReconcileTransactionsTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):

    ENDPOINT_VERB = 'post'

    def setUp(self):
        super().setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

        self._populate_transactions()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:reconcile-transactions')

    def _populate_transactions(self, tot=80):
        transactions = generate_transactions(transaction_batch=tot)

    def _get_authorised_user(self):
        return self.bank_admins[0]

    def test_reconcile_transactions(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.post(
            url, {'date': date.today().isoformat()}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        today = datetime.combine(date.today(), time.min).replace(
            tzinfo=timezone.get_current_timezone())
        transactions_today = Transaction.objects.filter(
            received_at__lt=today + timedelta(days=1),
            received_at__gte=today
        )

        for transaction in transactions_today:
            self.assertTrue(transaction.reconciled)

    def test_no_date_returns_bad_request(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.post(
            url, {}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_invalid_date_returns_bad_request(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.post(
            url, {'date': 'bleh'}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
