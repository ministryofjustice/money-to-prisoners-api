from django.core.urlresolvers import reverse

from rest_framework import status

from transaction.models import Transaction, Log
from transaction.constants import TRANSACTION_STATUS, LOG_ACTIONS
from transaction.api.bank_admin.views import TransactionView

from .utils import generate_transactions_data
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

    def _get_url(self, user=None, prison=None, status=None):
        return reverse('bank-admin:transaction-list')

    def _get_transactions_data(self, tot=30):
        data_list = generate_transactions_data(
            uploads=1,
            transaction_batch=tot,
            status=TRANSACTION_STATUS.AVAILABLE
        )

        create_serializer = TransactionView.create_serializer_class()
        keys = create_serializer.get_fields().keys()

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
