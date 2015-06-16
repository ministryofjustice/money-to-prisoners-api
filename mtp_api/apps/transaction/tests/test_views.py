from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from transaction.models import Transaction

from .utils import generate_transactions


class TransactionViewTestCase(APITestCase):

    def setUp(self):
        super(TransactionViewTestCase, self).setUp()
        generate_transactions(uploads=2, transaction_batch=21)

    def assertTransactionsInUpload(self, response, upload_counter):
        """
        Asserts that all the transactions in the response belong to
        the specific upload batch
        """
        uc = Transaction.objects.filter(
            id__in=[
                t['id'] for t in response.data['results']
            ]).values_list('upload_counter', flat=True).distinct()

        self.assertEqual(len(uc), 1)
        self.assertEqual(uc[0], upload_counter)

    def test_list_latest_upload(self):
        url = reverse('transaction-list')

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 21)
        self.assertNotEqual(response.data['next'], None)

        # get transaction from response data and make sure that they
        # all belong to last upload
        self.assertTransactionsInUpload(response, 2)

    def test_list_specific_upload(self):
        url = '%s?upload_counter=1' % reverse('transaction-list')

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 21)
        self.assertNotEqual(response.data['next'], None)

        # get transaction from response data and make sure that they
        # all belong to last upload
        self.assertTransactionsInUpload(response, 1)
        """
        Asserts that
        """
