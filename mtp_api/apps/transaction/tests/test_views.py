from rest_framework.settings import api_settings
from collections import Counter

from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, make_test_oauth_applications
from transaction.tests.utils import generate_transactions
from mtp_auth.models import PrisonUserMapping
from transaction.models import Transaction


def get_user_for_prison(prison):
    return PrisonUserMapping.objects.filter(prisons=prison).first().user


class TransactionViewTestCase(APITestCase):
    fixtures = ['test_prisons.json']

    def setUp(self):
        super(TransactionViewTestCase, self).setUp()
        self.transactions = generate_transactions(
            uploads=2, transaction_batch=101)
        make_test_users()
        make_test_oauth_applications()

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

    def calculate_prison_transaction_counts(self, upload_counter=None):
        if not upload_counter:
            upload_counter = max({x.upload_counter for x in self.transactions})

        return Counter([x.prison for x in self.transactions if x.upload_counter == upload_counter])

    def test_list_latest_upload(self):
        url = reverse('transaction-list')
        unique_prisons = self.calculate_prison_transaction_counts()
        for prison, count in unique_prisons.items():
            # we have to do if Prison because some transactions don't have a prison attached
            # and therefore no user will be able to see those...
            # TODO: figure out who is responsible for these transactions
            if prison:
                self.client.force_authenticate(
                    user=get_user_for_prison(prison))
                response = self.client.get(url, format='json')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['count'], count)
                if count > api_settings.PAGE_SIZE:
                    self.assertNotEqual(response.data['next'], None)

                # get transaction from response data and make sure that they
                # all belong to last upload
                self.assertTransactionsInUpload(response, 2)

    def test_list_specific_upload(self):
        upload_counter = 1
        url = '{url}?upload_counter={upload_counter}'.\
            format(
                url=reverse('transaction-list'),
                upload_counter=upload_counter
            )

        unique_prisons = self.calculate_prison_transaction_counts(
            upload_counter=upload_counter)
        for prison, count in unique_prisons.items():
            if prison:
                self.client.force_authenticate(
                    user=get_user_for_prison(prison))
                response = self.client.get(url, format='json')
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['count'], count)
                if count > api_settings.PAGE_SIZE:
                    self.assertNotEqual(response.data['next'], None)

                # get transaction from response data and make sure that they
                # all belong to last upload
                self.assertTransactionsInUpload(response, 1)

    def test_list_cant_access_if_not_authenticated(self):
        url = reverse('transaction-list')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
