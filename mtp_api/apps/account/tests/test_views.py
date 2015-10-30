from rest_framework import status
from rest_framework.test import APITestCase
from django.core.urlresolvers import reverse

from transaction.tests.utils import generate_transactions
from mtp_auth.tests.utils import AuthTestCaseMixin
from core.tests.utils import make_test_users
from account.models import File, FileType


class CreateFileViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['test_prisons.json', 'initial_file_types.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks, _, self.bank_admins, _ = make_test_users()

    def test_permissions_required(self):
        user = self.prison_clerks[0]
        test_transactions = generate_transactions(5)
        tid_list = [t.id for t in test_transactions]

        new_file = {
            'file_type': 4,
            'transactions': tid_list
        }

        response = self.client.post(
            reverse('file-list'), data=new_file, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_file_succeeds(self):
        user = self.bank_admins[0]
        test_transactions = generate_transactions(5)
        tid_list = [t.id for t in test_transactions]

        new_file = {
            'file_type': 4,
            'transactions': tid_list,
            'balance': {
                'opening_balance': 100,
                'closing_balance': 200
            }
        }

        response = self.client.post(
            reverse('file-list'), data=new_file, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        files = File.objects.all()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].file_type, FileType.objects.get(pk=4))
        self.assertEqual(files[0].balance.opening_balance, 100)
        self.assertEqual(files[0].balance.closing_balance, 200)
        self.assertEqual(len(files[0].transactions.all()), len(test_transactions))
        for transaction in files[0].transactions.all():
            self.assertTrue(transaction in test_transactions)

    def test_create_file_without_balance_succeeds(self):
        user = self.bank_admins[0]
        test_transactions = generate_transactions(5)
        tid_list = [t.id for t in test_transactions]

        new_file = {
            'file_type': 4,
            'transactions': tid_list
        }

        response = self.client.post(
            reverse('file-list'), data=new_file, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        files = File.objects.all()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].file_type, FileType.objects.get(pk=4))
        self.assertEqual(len(files[0].transactions.all()), len(test_transactions))
        for transaction in files[0].transactions.all():
            self.assertTrue(transaction in test_transactions)

        try:
            files[0].balance
            self.fail()
        except File.balance.RelatedObjectDoesNotExist:
            pass

    def test_create_file_without_file_type_fails(self):
        user = self.bank_admins[0]
        test_transactions = generate_transactions(5)
        tid_list = [t.id for t in test_transactions]

        new_file = {
            'transactions': tid_list
        }

        response = self.client.post(
            reverse('file-list'), data=new_file, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(File.objects.count(), 0)

    def test_create_file_without_transactions_fails(self):
        user = self.bank_admins[0]

        new_file = {
            'file_type': 4,
            'transactions': []
        }

        response = self.client.post(
            reverse('file-list'), data=new_file, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(File.objects.count(), 0)
