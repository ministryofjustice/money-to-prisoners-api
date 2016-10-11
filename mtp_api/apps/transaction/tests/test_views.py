from datetime import date, datetime, timedelta, time

from django.core.urlresolvers import reverse
from django.conf import settings
from django.utils import timezone
from rest_framework import status as http_status

from core.tests.utils import silence_logger
from credit.constants import LOG_ACTIONS
from credit.models import Credit, Log
from payment.models import Batch
from transaction.models import Transaction
from transaction.constants import TRANSACTION_CATEGORY, TRANSACTION_SOURCE
from transaction.serializers import CreateTransactionSerializer
from .utils import (
    generate_initial_transactions_data, generate_transactions, filters_from_api_data
)
from .test_base import (
    BaseTransactionViewTestCase, TransactionRejectsRequestsWithoutPermissionTestMixin
)


class CreateTransactionsTestCase(
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
        return self.bank_admins[0]

    def _get_url(self, *args, **kwargs):
        return reverse('transaction-list')

    def _get_transactions_data(self, tot=80):
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
            filters = filters_from_api_data(data)
            self.assertTrue(Transaction.objects.filter(**filters).exists())

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=user,
                action=LOG_ACTIONS.CREATED
            ).count(),
            len([data for data in data_list if
                 data['category'] == TRANSACTION_CATEGORY.CREDIT and
                 data['source'] == TRANSACTION_SOURCE.BANK_TRANSFER])
        )

    def test_create_with_debit_category(self):
        user = self.bank_admins[0]
        data_list = self._get_transactions_data(tot=1)
        data_list[0]['category'] = TRANSACTION_CATEGORY.DEBIT

        response = self.client.post(
            self._get_url(), data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        self.assertEqual(
            Transaction.objects.filter(category=TRANSACTION_CATEGORY.DEBIT).count(), 1
        )

    def test_create_with_administrative_source(self):
        user = self.bank_admins[0]
        data_list = self._get_transactions_data(tot=1)
        data_list[0]['source'] = TRANSACTION_SOURCE.ADMINISTRATIVE

        response = self.client.post(
            self._get_url(), data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        self.assertEqual(
            Transaction.objects.filter(source=TRANSACTION_SOURCE.ADMINISTRATIVE).count(), 1
        )

    def test_create_with_related_payment_batch(self):
        batch = Batch(date=date.today() - timedelta(days=3))
        batch.save()

        user = self.bank_admins[0]
        data_list = self._get_transactions_data(tot=1)
        data_list[0]['batch'] = batch.id

        response = self.client.post(
            self._get_url(), data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

        self.assertEqual(
            Transaction.objects.filter(batch=batch).count(), 1
        )
        self.assertIsNotNone(Batch.objects.first().settlement_transaction)


class CreateIncompleteTransactionsTestCase(
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
        return self.bank_admins[0]

    def _get_url(self, *args, **kwargs):
        return reverse('transaction-list')

    def _get_transactions_data(self, tot=30):
        data_list = generate_initial_transactions_data(tot=tot)

        serializer = CreateTransactionSerializer()
        keys = serializer.get_fields().keys()

        return [
            {k: data[k] for k in keys if k in data}
            for data in data_list
        ]

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

    def _create_list_with_missing_field(self, null_field):
        url = self._get_url()
        data_list = self._get_transactions_data()

        user = self.bank_admins[0]
        del data_list[0][null_field]

        return self.client.post(
            url, data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

    def test_create_list_missing_account_number_succeeds(self):
        response = self._create_list_with_missing_field('sender_account_number')
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

    def test_create_list_missing_sort_code_succeeds(self):
        response = self._create_list_with_missing_field('sender_sort_code')
        self.assertEqual(response.status_code, http_status.HTTP_201_CREATED)

    def test_create_list_missing_amount_fails(self):
        current_count = Transaction.objects.count()

        response = self._create_list_with_missing_field('amount')

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        # check no change in db
        self.assertEqual(current_count, Transaction.objects.count())


class UpdateRefundTransactionsTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):

    ENDPOINT_VERB = 'patch'

    def setUp(self):
        super().setUp()

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
        return reverse('transaction-list')

    def _get_transactions(self, tot=30):
        transactions = generate_transactions(transaction_batch=tot)

        data_list = []
        for i, trans in enumerate(transactions):
            refund = False
            if trans.credit and trans.credit.refund_pending:
                refund = True
            data_list.append({'id': trans.id, 'refunded': refund})

        return data_list

    def test_patch_refunded(self):
        """
        PATCH on endpoint should update status of given transactions
        """

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
                self.assertTrue(Transaction.objects.get(id=data['id']).credit.refunded)

        # check logs
        refunded_data_list = [t['id'] for t in data_list if t['refunded']]
        self.assertEqual(
            Log.objects.filter(
                user=user,
                action=LOG_ACTIONS.REFUNDED
            ).count(),
            len(refunded_data_list)
        )

    def _patch_refunded_with_invalid_status(self, valid_data_list, status):
        url = self._get_url()
        user = self._get_authorised_user()

        invalid_transactions = Transaction.objects.filter(
            Transaction.STATUS_LOOKUP[status])
        invalid_data_list = (
            [{'id': t.id, 'refunded': True} for t in invalid_transactions]
        )

        with silence_logger():
            return self.client.patch(
                url, data=valid_data_list + invalid_data_list, format='json',
                HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
            )

    def test_patch_credited_creates_conflict(self):
        valid_data_list = self._get_transactions()
        response = self._patch_refunded_with_invalid_status(
            valid_data_list, 'creditable')

        self.assertEqual(response.status_code, http_status.HTTP_409_CONFLICT)

        # check that entire update failed
        for data in valid_data_list:
            if data['refunded']:
                self.assertFalse(
                    Transaction.objects.get(id=data['id']).credit.refunded
                )

    def test_patch_refunded_creates_conflict(self):
        valid_data_list = self._get_transactions()
        response = self._patch_refunded_with_invalid_status(
            valid_data_list, 'refundable')

        self.assertEqual(response.status_code, http_status.HTTP_409_CONFLICT)

        # check that entire update failed
        for data in valid_data_list:
            if data['refunded']:
                self.assertFalse(
                    Transaction.objects.get(id=data['id']).credit.refunded
                )

    def test_patch_cannot_update_disallowed_fields(self):
        """
        PATCH should not update fields other than refunded
        """

        url = self._get_url()
        data_list = self._get_transactions()
        for item in data_list:
            item['amount'] = '999999999'

        user = self._get_authorised_user()

        response = self.client.patch(
            url, data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        # check lack changes in db
        for data in data_list:
            self.assertNotEqual(
                Transaction.objects.get(id=data['id']).amount,
                data['amount']
            )


class GetTransactionsBaseTestCase(
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
        return reverse('transaction-list')

    def _populate_transactions(self, tot=80):
        return generate_transactions(transaction_batch=tot)

    def _get_authorised_user(self):
        return self.bank_admins[0]


class GetTransactionsAsBankAdminTestCase(GetTransactionsBaseTestCase):

    def _get_with_status(self, user, status):
        url = self._get_url()

        response = self.client.get(
            url, {'status': status, 'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        return response.data

    def _test_get_list_with_status(self, status):
        data = self._get_with_status(self._get_authorised_user(),
                                     status)

        # check that all matching db records are returned
        ts = list(Transaction.objects.filter(
            Transaction.STATUS_LOOKUP[status]))
        db_ids = [t.id for t in ts]
        self.assertEqual(len(set(db_ids)), len(data['results']))

        # check that all results match the provided status
        for t in data['results']:
            self.assertEqual(Transaction.objects.filter(
                Transaction.STATUS_LOOKUP[status], id=t['id']).count(), 1)

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

    def _test_get_list_with_status_verify_fields(self, status):
        results = self._test_get_list_with_status(status)
        self._assert_required_fields_present(results)
        self._assert_hidden_fields_absent(results)
        return results

    def test_get_list_all(self):
        data = self._get_with_status(self._get_authorised_user(), '')

        self.assertEqual(len(data['results']), len(Transaction.objects.all()))
        self._assert_required_fields_present(data['results'])
        self._assert_hidden_fields_absent(data['results'])

    def test_get_list_refundable(self):
        self._test_get_list_with_status_verify_fields('refundable')

    def test_get_list_creditable(self):
        self._test_get_list_with_status_verify_fields('creditable')

    def test_get_list_invalid_status_returns_no_results(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.get(
            url, {'status': 'not_a_real_status'}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(len(response.data['results']), 0)


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


class GetTransactionsFilteredByDateTestCase(GetTransactionsBaseTestCase):

    def test_get_list_received_between_dates(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.get(
            url, {'received_at__lt': self._get_latest_date(),
                  'received_at__gte': self._get_latest_date() - timedelta(days=2),
                  'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        results = response.data['results']
        result_ids = [t['id'] for t in results]
        yesterday = timezone.make_aware(datetime.combine(self._get_latest_date(), time.min))
        received_between_dates = Transaction.objects.filter(
            received_at__lt=yesterday,
            received_at__gte=(yesterday - timedelta(days=2))
        )
        self.assertEqual(len(result_ids), len(received_between_dates))

        for trans in received_between_dates:
            self.assertTrue(trans.id in result_ids)

    def test_get_list_ordered_by_date(self):
        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.get(
            url, {'ordering': '-received_at',
                  'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        results = response.data['results']
        db_transactions = Transaction.objects.all().order_by('-received_at')
        self.assertEqual(len(results), len(db_transactions))

        for db_trans, response_trans in zip(db_transactions, results):
            self.assertEqual(
                db_trans.received_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
                response_trans['received_at']
            )

    def test_get_list_received_between_datetimes(self):
        url = self._get_url()
        user = self._get_authorised_user()

        start_date = datetime.combine(
            self._get_latest_date() - timedelta(days=2),
            time(10, 0, tzinfo=timezone.utc)
        )
        end_date = datetime.combine(
            self._get_latest_date(),
            time(22, 0, tzinfo=timezone.utc)
        )

        response = self.client.get(
            url, {'received_at__lt': end_date.isoformat(),
                  'received_at__gte': start_date.isoformat(),
                  'limit': 1000}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        results = response.data['results']
        result_ids = [t['id'] for t in results]
        received_between_dates = Transaction.objects.filter(
            received_at__lt=end_date,
            received_at__gte=start_date
        )
        self.assertEqual(len(result_ids), len(received_between_dates))

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
        return reverse('reconcile-transactions')

    def _populate_transactions(self, tot=100):
        return generate_transactions(transaction_batch=tot)

    def _get_authorised_user(self):
        return self.bank_admins[0]

    def _get_date_bounds(self):
        start_date = datetime.combine(
            self._get_latest_date() - timedelta(days=1),
            time(23, 0, tzinfo=timezone.utc)
        )
        end_date = datetime.combine(
            self._get_latest_date(),
            time(23, 0, tzinfo=timezone.utc)
        )
        return start_date, end_date

    def test_reconcile_transactions(self):
        url = self._get_url()
        user = self._get_authorised_user()

        start_date, end_date = self._get_date_bounds()

        response = self.client.post(
            url, {'received_at__gte': start_date, 'received_at__lt': end_date},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        transactions_from_period = Transaction.objects.filter(
            received_at__lt=end_date,
            received_at__gte=start_date
        )

        for transaction in transactions_from_period:
            if transaction.credit:
                self.assertTrue(transaction.credit.reconciled)

    def test_reconciliation_logs_are_not_duplicated(self):
        start_date, end_date = self._get_date_bounds()

        credits_yesterday = Credit.objects.filter(
            received_at__lt=end_date,
            received_at__gte=start_date
        )

        url = self._get_url()
        user = self._get_authorised_user()

        response = self.client.post(
            url,
            {'received_at__gte': start_date.isoformat(),
             'received_at__lt': end_date.isoformat()},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=user,
                action=LOG_ACTIONS.RECONCILED,
            ).count(),
            len(credits_yesterday)
        )

        response = self.client.post(
            url,
            {'received_at__gte': start_date.isoformat(),
             'received_at__lt': end_date.isoformat()},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        # check logs again
        self.assertEqual(
            Log.objects.filter(
                user=user,
                action=LOG_ACTIONS.RECONCILED,
            ).count(),
            len(credits_yesterday)
        )

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
            url, {'start_date': 'bleh', 'end_date': 'yeeeah'}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_reconciliation_populates_ref_code(self):
        url = self._get_url()
        user = self._get_authorised_user()

        start_date, end_date = self._get_date_bounds()

        response = self.client.post(
            url,
            {'received_at__gte': start_date.isoformat(),
             'received_at__lt': end_date.isoformat()},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        # debits not given ref code
        qs = Transaction.objects.filter(
            category=TRANSACTION_CATEGORY.DEBIT,
            received_at__gte=start_date,
            received_at__lt=end_date
        )
        for trans in qs:
            self.assertEqual(trans.ref_code, None)

        # anomalous not given ref code
        qs = Transaction.objects.filter(
            source=TRANSACTION_SOURCE.ADMINISTRATIVE,
            received_at__gte=start_date,
            received_at__lt=end_date
        )
        for trans in qs:
            self.assertEqual(trans.ref_code, None)

        # valid credits, refunds and rejects given ref code
        qs = Transaction.objects.filter(
            category=TRANSACTION_CATEGORY.CREDIT,
            source=TRANSACTION_SOURCE.BANK_TRANSFER,
            received_at__gte=start_date,
            received_at__lt=end_date
        ).order_by('id')

        expected_ref_code = settings.REF_CODE_BASE
        for trans in qs:
            self.assertEqual(trans.ref_code, str(expected_ref_code))
            expected_ref_code += 1

    def test_reconciliation_populates_ref_code_from_batch(self):
        url = self._get_url()
        user = self._get_authorised_user()

        start_date, end_date = self._get_date_bounds()

        administrative_trans = Transaction.objects.filter(
            category=TRANSACTION_CATEGORY.CREDIT,
            received_at__gte=start_date,
            received_at__lt=end_date
        ).first()
        administrative_trans.source = TRANSACTION_SOURCE.ADMINISTRATIVE
        administrative_trans.save()
        batch = Batch(date=self._get_latest_date() - timedelta(days=3),
                      settlement_transaction=administrative_trans,
                      ref_code='800003')
        batch.save()

        response = self.client.post(
            url,
            {'received_at__gte': start_date.isoformat(),
             'received_at__lt': end_date.isoformat()},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_204_NO_CONTENT)

        trans = Transaction.objects.get(
            batch__isnull=False,
            received_at__gte=start_date,
            received_at__lt=end_date
        )
        self.assertEqual(trans.ref_code, batch.ref_code)
