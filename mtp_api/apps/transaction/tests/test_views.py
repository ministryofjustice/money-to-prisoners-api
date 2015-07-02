import urllib.parse

from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, make_test_oauth_applications
from mtp_auth.models import PrisonUserMapping

from prison.models import Prison

from transaction.constants import TRANSACTION_STATUS

from .utils import generate_transactions


def get_users_for_prison(prison):
    return [m.user for m in PrisonUserMapping.objects.filter(prisons=prison)]


def get_prisons_for_user(user):
    return PrisonUserMapping.objects.get(user=user).prisons.all()


class BaseTransactionViewTestCase(APITestCase):
    fixtures = ['test_prisons.json']
    STATUS_FILTERS = {
        None: lambda t: True,
        TRANSACTION_STATUS.PENDING: lambda t: t.owner and not t.credited,
        TRANSACTION_STATUS.AVAILABLE: lambda t: not t.owner and not t.credited,
        TRANSACTION_STATUS.CREDITED: lambda t: t.owner and t.credited
    }

    def setUp(self):
        super(BaseTransactionViewTestCase, self).setUp()
        self.owners = make_test_users(users_per_prison=2)
        self.transactions = generate_transactions(
            uploads=1, transaction_batch=101
        )
        self.prisons = Prison.objects.all()
        make_test_oauth_applications()


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

    def _request_and_assert(self, status_param=None):
        for prison in self.prisons:
            expected_ids = [
                t.pk for t in self.transactions if
                    t.prison == prison and
                    self.STATUS_FILTERS[status_param](t)
            ]
            url = self._get_list_url(prison, status=status_param)

            expected_owners = get_users_for_prison(prison)
            self.client.force_authenticate(user=expected_owners[0])

            response = self.client.get(url, format='json')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['count'], len(expected_ids))

            self.assertListEqual(
                sorted([t['id'] for t in response.data['results']]),
                sorted(expected_ids)
            )

    def _get_list_url(self, prison, status=None):
        url = reverse(
            'transaction-prison-list', kwargs={
                'prison_id': prison.pk
            }
        )

        params = {
            'limit': 10000
        }
        if status:
            params['status'] = status

        return '{url}?{params}'.format(
            url=url, params=urllib.parse.urlencode(params)
        )

    def test_all(self):
        """
        GET without params should return all transactions linked
        to that prison.
        """
        self._request_and_assert()

    def test_with_pending_status(self):
        self._request_and_assert(
            status_param=TRANSACTION_STATUS.PENDING
        )

    def test_with_available_status(self):
        self._request_and_assert(
            status_param=TRANSACTION_STATUS.AVAILABLE
        )

    def test_with_credited_status(self):
        self._request_and_assert(
            status_param=TRANSACTION_STATUS.CREDITED
        )


class TransactionsByPrisonAndUserEndpointTestCase(BaseTransactionViewTestCase):

    def _request_and_assert(self, status_param=None):
        for owner in self.owners:
            self.client.force_authenticate(user=owner)

            prisons = get_prisons_for_user(owner)

            for prison in prisons:
                expected_ids = [
                    t.pk for t in self.transactions if
                        t.prison == prison and
                        t.owner == owner and
                        self.STATUS_FILTERS[status_param](t)
                ]
                url = self._get_list_url(owner, prison, status=status_param)

                response = self.client.get(url, format='json')

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['count'], len(expected_ids))

                self.assertListEqual(
                    sorted([t['id'] for t in response.data['results']]),
                    sorted(expected_ids)
                )

    def _get_list_url(self, owner, prison, status=None):
        url = reverse(
            'transaction-prison-user-list', kwargs={
                'user_id': owner.pk,
                'prison_id': prison.pk
            }
        )

        params = {
            'limit': 10000
        }
        if status:
            params['status'] = status

        return '{url}?{params}'.format(
            url=url, params=urllib.parse.urlencode(params)
        )

    def test_all(self):
        self._request_and_assert()

    def test_with_pending_status(self):
        self._request_and_assert(
            status_param=TRANSACTION_STATUS.PENDING
        )

    def test_with_available_status(self):
        self._request_and_assert(
            status_param=TRANSACTION_STATUS.AVAILABLE
        )

    def test_with_credited_status(self):
        self._request_and_assert(
            status_param=TRANSACTION_STATUS.CREDITED
        )
