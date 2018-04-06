from datetime import date, timedelta

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import Balance
from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin


class CreateBalanceTestCase(AuthTestCaseMixin, APITestCase):

    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.bank_admins = test_users['bank_admins']

    def test_permissions_required(self):
        user = self.prison_clerks[0]

        new_balance = {
            'closing_balance': 20000,
            'date': date.today()
        }

        response = self.client.post(
            reverse('balance-list'), data=new_balance, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_balance_succeeds(self):
        user = self.bank_admins[0]

        new_balance = {
            'closing_balance': 20000,
            'date': date.today()
        }

        response = self.client.post(
            reverse('balance-list'), data=new_balance, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        balances = Balance.objects.all()
        self.assertEqual(balances.count(), 1)
        self.assertEqual(balances[0].closing_balance, 20000)
        self.assertEqual(balances[0].date, date.today())

    def test_create_balance_only_allows_one_per_date(self):
        user = self.bank_admins[0]
        balance_date = date.today()

        new_balance = {
            'closing_balance': 20000,
            'date': balance_date
        }
        response = self.client.post(
            reverse('balance-list'), data=new_balance, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        new_balance = {
            'closing_balance': 40000,
            'date': balance_date
        }
        response = self.client.post(
            reverse('balance-list'), data=new_balance, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        balances = Balance.objects.all()
        self.assertEqual(balances.count(), 1)
        self.assertEqual(balances[0].closing_balance, 20000)
        self.assertEqual(balances[0].date, balance_date)


class ListBalanceViewTestCase(AuthTestCaseMixin, APITestCase):

    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.prison_clerks = test_users['prison_clerks']
        self.bank_admins = test_users['bank_admins']

    def test_get_balance_is_ordered_by_date_desc(self):
        user = self.bank_admins[0]

        # first balance
        balance1 = Balance.objects.create(closing_balance=10000,
                                          date=date.today() - timedelta(days=1))

        # second balance
        balance2 = Balance.objects.create(closing_balance=20000,
                                          date=date.today())

        response = self.client.get(
            reverse('balance-list'), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        results = response.data['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['id'], balance2.id)
        self.assertEqual(results[1]['id'], balance1.id)

    def test_get_balance_less_than_date(self):
        user = self.bank_admins[0]

        # first balance
        balance1 = Balance.objects.create(closing_balance=10000,
                                          date=date.today() - timedelta(days=1))

        # second balance
        Balance.objects.create(closing_balance=20000,
                               date=date.today())

        response = self.client.get(
            reverse('balance-list'), {'date__lt': date.today().isoformat()},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )

        results = response.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], balance1.id)
