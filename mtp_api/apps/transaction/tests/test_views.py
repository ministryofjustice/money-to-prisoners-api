from rest_framework.settings import api_settings
from collections import Counter

from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, make_test_oauth_applications
from transaction.tests.utils import generate_transactions
from mtp_auth.models import PrisonUserMapping

from transaction.models import Transaction
from transaction.constants import TRANSACTION_STATUS


def get_users_for_prison(prison):
    return [m.user for m in PrisonUserMapping.objects.filter(prisons=prison)]


def get_prisons_for_user(user):
    return PrisonUserMapping.objects.get(user=user).prisons.all()


class BaseTransactionViewTestCase(APITestCase):
    fixtures = ['test_prisons.json']

    def setUp(self):
        super(BaseTransactionViewTestCase, self).setUp()
        make_test_users(users_per_prison=2)
        self.transactions = generate_transactions(
            uploads=2, transaction_batch=101
        )
        make_test_oauth_applications()

    def calculate_prison_transaction_counts(self, filter_):
        filter_ = filter_ or (lambda x: True)
        return Counter([t.prison for t in self.transactions if filter_(t)])

    def calculate_owner_transaction_counts(self, filter_):
        filter_ = filter_ or (lambda x: True)
        return Counter([t.owner for t in self.transactions if filter_(t)])

    def assertResultsBelongToUser(self, results, user):
        if not results:
            return

        ids = {x['id'] for x in results}

        user_prisons = set(user.prisonusermapping.prisons.values_list('pk', flat=True))

        self.assertEqual(
            Transaction.objects.filter(id__in=ids, prison_id__in=user_prisons).count(),
            len(results)
        )


class TransactionsEndpointTestCase(BaseTransactionViewTestCase):

    def test_cant_access(self):
        """
        GET on transactions endpoint should 404.
        """
        url = reverse('transaction-list')

        # authenticate, just in case
        prison = [t.prison for t in self.transactions if t.prison][0]
        user = get_users_for_prison(prison)[0]
        self.client.force_authenticate(user=user)

        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TransactionsByPrisonEndpointTestCase(BaseTransactionViewTestCase):

    def _request_and_assert(self, prison, expected_count, status_param=None):
        url = self._get_list(prison, status=status_param)

        expected_owners = get_users_for_prison(prison)
        self.client.force_authenticate(user=expected_owners[0])

        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], expected_count)

        # there should be more than 1 owners as we are not filtering
        # by user
        self.assertEqual(
            set([r['owner'] for r in response.data['results']]),
            {o.pk for o in expected_owners}
        )
        if expected_count > api_settings.PAGE_SIZE:
            self.assertNotEqual(response.data['next'], None)

    def _get_list(self, prison, status=None):
        url = reverse(
            'transaction-prison-list', kwargs={
                'prison_id': prison.pk
            }
        )

        if status:
            url = '{url}?status={status}'.format(
                url=url, status=status
            )
        return url

    def test_all(self):
        """
        GET without params should return all transactions linked
        to that prison.
        """
        prisons_n_counters = self.calculate_prison_transaction_counts(
            lambda t: t.prison
        )
        self.assertNotEqual(len(prisons_n_counters), 0)

        for prison, count in prisons_n_counters.items():
            self._request_and_assert(prison, count)

    def test_with_pending_status(self):
        prisons_n_counters = self.calculate_prison_transaction_counts(
            lambda t: t.prison and t.owner and not t.credited
        )
        self.assertNotEqual(len(prisons_n_counters), 0)

        for prison, count in prisons_n_counters.items():
            self._request_and_assert(
                prison, count, status_param=TRANSACTION_STATUS.PENDING
            )

    def test_with_available_status(self):
        prisons_n_counters = self.calculate_prison_transaction_counts(
            lambda t: t.prison and not t.owner and not t.credited
        )
        self.assertNotEqual(len(prisons_n_counters), 0)

        for prison, count in prisons_n_counters.items():
            self._request_and_assert(
                prison, count, status_param=TRANSACTION_STATUS.AVAILABLE
            )

    def test_with_credited_status(self):
        prisons_n_counters = self.calculate_prison_transaction_counts(
            lambda t: t.prison and t.owner and t.credited
        )
        self.assertNotEqual(len(prisons_n_counters), 0)

        for prison, count in prisons_n_counters.items():
            self._request_and_assert(
                prison, count, status_param=TRANSACTION_STATUS.CREDITED
            )


class TransactionsByPrisonAndUserEndpointTestCase(BaseTransactionViewTestCase):

    def _request_and_assert(self, owner, expected_count, status_param=None):
        self.client.force_authenticate(user=owner)

        prisons = get_prisons_for_user(owner)

        results = []
        count = 0
        for prison in prisons:
            url = self._get_list(owner, prison, status=status_param)

            response = self.client.get(url, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            results += response.data['results']
            count += response.data['count']

        self.assertEqual(count, expected_count)

    def _get_list(self, owner, prison, status=None):
        url = reverse(
            'transaction-prison-user-take', kwargs={
                'user_id': owner.pk,
                'prison_id': prison.pk
            }
        )

        if status:
            url = '{url}?status={status}'.format(
                url=url, status=status
            )
        return url

    def test_all(self):
        """
        """
        owners_n_counters = self.calculate_owner_transaction_counts(
            lambda t: t.owner
        )
        for owner, count in owners_n_counters.items():
            self._request_and_assert(owner, count)

    def test_with_pending_status(self):
        owners_n_counters = self.calculate_owner_transaction_counts(
            lambda t: t.owner and not t.credited
        )
        for owner, count in owners_n_counters.items():
            self._request_and_assert(
                owner, count, status_param=TRANSACTION_STATUS.PENDING
            )

    def test_with_available_status(self):
        owners = [m.user for m in PrisonUserMapping.objects.all()]
        for owner in owners:
            self._request_and_assert(
                owner, 0, status_param=TRANSACTION_STATUS.AVAILABLE
            )

    def test_with_credited_status(self):
        owners_n_counters = self.calculate_owner_transaction_counts(
            lambda t: t.owner and t.credited
        )
        for owner, count in owners_n_counters.items():
            self._request_and_assert(
                owner, count, status_param=TRANSACTION_STATUS.CREDITED
            )
