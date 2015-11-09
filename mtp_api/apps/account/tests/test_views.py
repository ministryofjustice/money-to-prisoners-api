from rest_framework import status
from rest_framework.test import APITestCase
from django.core.urlresolvers import reverse

from transaction.tests.utils import generate_transactions
from mtp_auth.tests.utils import AuthTestCaseMixin
from core.tests.utils import make_test_users
from account.models import Batch


class CreateBatchViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, self.bank_admins, _ = make_test_users()

    def test_permissions_required(self):
        user = self.prison_clerks[0]
        test_transactions = generate_transactions(5)
        tid_list = [t.id for t in test_transactions]

        new_batch = {
            'label': 'BAI2',
            'transactions': tid_list
        }

        response = self.client.post(
            reverse('batch-list'), data=new_batch, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_batch_succeeds(self):
        user = self.bank_admins[0]
        test_transactions = generate_transactions(5)
        tid_list = [t.id for t in test_transactions]

        new_batch = {
            'label': 'BAI2',
            'transactions': tid_list,
            'balance': {
                'opening_balance': 100,
                'closing_balance': 200
            }
        }

        response = self.client.post(
            reverse('batch-list'), data=new_batch, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        batches = Batch.objects.all()
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].label, 'BAI2')
        self.assertEqual(batches[0].balance.opening_balance, 100)
        self.assertEqual(batches[0].balance.closing_balance, 200)
        self.assertEqual(len(batches[0].transactions.all()), len(test_transactions))
        for transaction in batches[0].transactions.all():
            self.assertTrue(transaction in test_transactions)

    def test_create_batch_without_balance_succeeds(self):
        user = self.bank_admins[0]
        test_transactions = generate_transactions(5)
        tid_list = [t.id for t in test_transactions]

        new_batch = {
            'label': 'BAI2',
            'transactions': tid_list
        }

        response = self.client.post(
            reverse('batch-list'), data=new_batch, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        batches = Batch.objects.all()
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].label, 'BAI2')
        self.assertEqual(len(batches[0].transactions.all()), len(test_transactions))
        for transaction in batches[0].transactions.all():
            self.assertTrue(transaction in test_transactions)

        try:
            batches[0].balance
            self.fail()
        except Batch.balance.RelatedObjectDoesNotExist:
            pass

    def test_create_batch_without_label_fails(self):
        user = self.bank_admins[0]
        test_transactions = generate_transactions(5)
        tid_list = [t.id for t in test_transactions]

        new_batch = {
            'transactions': tid_list
        }

        response = self.client.post(
            reverse('batch-list'), data=new_batch, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Batch.objects.count(), 0)

    def test_create_batch_without_transactions_fails(self):
        user = self.bank_admins[0]

        new_batch = {
            'label': 'BAI2',
            'transactions': []
        }

        response = self.client.post(
            reverse('batch-list'), data=new_batch, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Batch.objects.count(), 0)


class ListBatchViewTestCase(AuthTestCaseMixin, APITestCase):

    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, self.bank_admins, _ = make_test_users()

    def test_get_batch_by_type(self):
        user = self.bank_admins[0]

        # bai2 batch
        test_transactions = generate_transactions(5)

        bai2_batch = Batch()
        bai2_batch.label = 'BAI2'
        bai2_batch.save()
        bai2_batch.transactions = test_transactions
        bai2_batch.save()

        # ADIREFUND batch
        test_transactions = generate_transactions(5)

        adi_batch = Batch()
        adi_batch.label = 'ADIREFUND'
        adi_batch.save()
        adi_batch.transactions = test_transactions
        adi_batch.save()

        response = self.client.get(
            reverse('batch-list'), {'label': 'ADIREFUND'}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], adi_batch.id)

    def test_get_batch_is_ordered_by_date_desc(self):
        user = self.bank_admins[0]

        # first ADIREFUND batch
        test_transactions = generate_transactions(5)

        adi_batch1 = Batch()
        adi_batch1.label = 'ADIREFUND'
        adi_batch1.save()
        adi_batch1.transactions = test_transactions
        adi_batch1.save()

        # second ADIREFUND batch
        test_transactions = generate_transactions(5)

        adi_batch2 = Batch()
        adi_batch2.label = 'ADIREFUND'
        adi_batch2.save()
        adi_batch2.transactions = test_transactions
        adi_batch2.save()

        response = self.client.get(
            reverse('batch-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        results = response.data['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['id'], adi_batch2.id)
        self.assertEqual(results[1]['id'], adi_batch1.id)
