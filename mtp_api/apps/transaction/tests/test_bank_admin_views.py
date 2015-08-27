import json

from django.core.urlresolvers import reverse
from rest_framework import status

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
            uploads=1,
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
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

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

    def _get_authorised_user(self):
        return self.bank_admins[0]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-patch')

    def _get_transactions(self, tot=30):
        transactions = generate_transactions(transaction_batch=tot)

        data_list = []
        for i, trans in enumerate(transactions):
            trans.save()
            refund = True
            if i % 5:
                refund = False
            data_list.append({'id': trans.id, 'refunded': refund})

        return data_list

    def test_patch_list(self):
        """PATCH on endpoint should update refunded status of given transactions"""

        url = self._get_url()
        data_list = self._get_transactions()

        user = self.bank_admins[0]

        response = self.client.patch(
            url, data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # check changes in db
        for data in data_list:
            self.assertEqual(
                Transaction.objects.get(id=data['id']).refunded, data['refunded']
            )

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

    def test_patch_list_disallowed_fields(self):
        """ PATCH should not update fields other than refunded """

        url = self._get_url()
        data_list = self._get_transactions()
        for item in data_list:
            item['prisoner_number'] = 'AAAAAAA'

        user = self.bank_admins[0]

        response = self.client.patch(
            url, data=data_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # check lack changes in db
        for data in data_list:
            self.assertNotEqual(
                Transaction.objects.get(id=data['id']).prisoner_number, data['prisoner_number']
            )


class GetTransactionsTestCase(
    TransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):
    ENDPOINT_VERB = 'get'

    def setUp(self):
        super(GetTransactionsTestCase, self).setUp()

        # delete all transactions and logs
        Transaction.objects.all().delete()
        Log.objects.all().delete()

        data_list = self._populate_transactions()

    def _get_unauthorised_application_users(self):
        return [
            self.prison_clerks[0], self.prisoner_location_admins[0]
        ]

    def _get_authorised_user(self):
        return self.bank_admins[0]

    def _get_url(self, *args, **kwargs):
        return reverse('bank_admin:transaction-list')

    def _populate_transactions(self, tot=10):
        transactions = generate_transactions(transaction_batch=tot)

        for i, trans in enumerate(transactions):
            if i % 6 == 0:
                trans.credited = True
            elif i % 5 == 0:
                trans.prisoner_number = ''
                if i % 2 == 0:
                    trans.refunded = True

            trans.save()

    def _get_with_status(self, status_arg):
        url = self._get_url()
        user = self.bank_admins[0]

        response = self.client.get(
            url, {'status': status_arg}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        return response.data

    def test_get_credited_refunded_list(self):
        data = self._get_with_status('credited,refunded')

        num_credited = Transaction.objects.filter(
            **Transaction.STATUS_LOOKUP['credited']).count()
        num_refunded = Transaction.objects.filter(
            **Transaction.STATUS_LOOKUP['refunded']).count()
        self.assertEqual(num_credited + num_refunded, len(data['results']))

        for t in data['results']:
            trans = Transaction.objects.get(id=t['id'])
            self.assertTrue(trans.credited or trans.refunded)

    def test_get_refund_pending_list(self):
        data = self._get_with_status('refund_pending')

        num_pending = Transaction.objects.filter(
            **Transaction.STATUS_LOOKUP['refund_pending']).count()
        self.assertEqual(num_pending, len(data['results']))

        for t in data['results']:
            trans = Transaction.objects.get(id=t['id'])
            self.assertTrue(not trans.refunded and trans.prisoner_number == '')
