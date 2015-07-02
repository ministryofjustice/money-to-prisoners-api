import random
import urllib.parse

from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, make_test_oauth_applications
from mtp_auth.models import PrisonUserMapping

from prison.models import Prison

from transaction.models import Transaction
from transaction.constants import TRANSACTION_STATUS, TAKE_LIMIT

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

    def _get_pending_transactions_qs(self, prison, user=None):
        params = {
            'credited': False,
            'prison': prison
        }
        if user:
            params['owner'] = user
        else:
            params['owner__isnull'] = False

        return Transaction.objects.filter(**params)

    def _get_available_transactions_qs(self, prison):
        return Transaction.objects.filter(
            owner__isnull=True, credited=False, prison=prison
        )

    def _get_credited_transactions_qs(self, user, prison):
        return Transaction.objects.filter(
            owner=user, credited=True, prison=prison
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

    def test_fails_with_logged_in_managing_different_prison(self):
        logged_in_user_prison = self.prisons[0]
        other_prison = self.prisons[1]

        logged_in_user = get_users_for_prison(logged_in_user_prison)[0]

        url = self._get_list_url(other_prison)

        self.client.force_authenticate(user=logged_in_user)

        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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

    def test_fails_with_logged_in_managing_different_prison(self):
        logged_in_user_prison = self.prisons[0]
        other_prison = self.prisons[1]

        logged_in_user = get_users_for_prison(logged_in_user_prison)[0]
        other_user = get_users_for_prison(other_prison)[0]

        url = self._get_list_url(other_user, other_prison)

        self.client.force_authenticate(user=logged_in_user)

        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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


class TransactionsTakeTestCase(BaseTransactionViewTestCase):

    def _get_url(self, user, prison, count=None):
        url = reverse(
            'transaction-prison-user-take', kwargs={
                'user_id': user.pk,
                'prison_id': prison.pk
            }
        )

        if count:
            url += '?count={count}'.format(count=count)

        return url

    def test_take_within_limit(self):
        prison = self.prisons[0]
        owner = get_users_for_prison(prison)[0]

        count = 1

        # delete pending transactions just to clean things up
        self._get_pending_transactions_qs(prison, owner).delete()

        # check no taken transactions in db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, owner).count(),
            0
        )

        # request
        self.client.force_authenticate(user=owner)

        url = self._get_url(owner, prison, count)
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_303_SEE_OTHER)

        # check 5 taken transactions in db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, owner).count(),
            count
        )

    def test_nobody_else_can_take_transactions_for_others(self):
        """
        Anybody managing a prison should be able to take transactions
        on behalf of other users within the same prison.
        """
        prison = self.prisons[0]
        users = get_users_for_prison(prison)
        self.assertTrue(len(users) >= 2)

        # We need 2 users as we want to test that logged_in_user
        # can take transactions on behalf of transactions_owner.
        # As result, the transactions.owner should be transactions_owner
        # and not logged_in_user
        logged_in_user = users[0]
        transactions_owner = users[1]

        # delete pending transactions just to clean things up
        self._get_pending_transactions_qs(prison, transactions_owner).delete()

        # check no taken transactions in db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, transactions_owner).count(),
            0
        )

        # request
        self.client.force_authenticate(user=logged_in_user)

        url = self._get_url(transactions_owner, prison, 1)
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # check 5 taken transactions in db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, transactions_owner).count(),
            0
        )

    def test_fails_when_taking_too_many(self):
        """
        Tests that fails when trying to take more than TAKE_LIMIT.
        """
        user = self.owners[0]
        prison = get_prisons_for_user(user)[0]

        # clean things up
        self._get_pending_transactions_qs(prison).update(owner=None)

        # make sure we have enough available transactions
        self.assertTrue(
            self._get_available_transactions_qs(prison).count() > TAKE_LIMIT
        )

        # check no taken transactions in db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, user).count(), 0
        )

        # request TAKE_LIMIT-1
        count = TAKE_LIMIT-1
        self.client.force_authenticate(user=user)

        url = self._get_url(user, prison, count)
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_303_SEE_OTHER)

        # check TAKE_LIMIT-1 taken transactions in db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, user).count(), count
        )

        # request 2 more => should fail
        url = self._get_url(user, prison, 2)
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # check still TAKE_LIMIT-1 taken transactions in db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, user).count(), count
        )


class TransactionsReleaseTestCase(BaseTransactionViewTestCase):

    def _get_url(self, user, prison):
        return reverse(
            'transaction-prison-user-release', kwargs={
                'user_id': user.pk,
                'prison_id': prison.pk
            }
        )

    def test_cannot_release_somebody_else_s_transactions_in_different_prison(self):
        """
        Tests that logged_in_user managing prison1 cannot release any
        transactions for prison2
        """
        prison1 = self.prisons[0]
        prison2 = self.prisons[1]

        logged_in_user = get_users_for_prison(prison1)[0]
        transactions_owner = get_users_for_prison(prison2)[0]

        pending_transactions = list(
            self._get_pending_transactions_qs(prison2, transactions_owner)
        )

        # if this starts failing, we need to iterate over users and get the
        # first user with pending transactions.
        self.assertTrue(len(pending_transactions) > 0)

        # request
        self.client.force_authenticate(user=logged_in_user)

        url = self._get_url(transactions_owner, prison2)
        response = self.client.post(url, {
            'transaction_ids': [t.id for t in pending_transactions]
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_can_release_somebody_else_s_transactions(self):
        """
        Tests that anybody managing the same prison can release
        somebody's pending transactions.
        """
        # We need 2 users as we want to test that logged_in_user
        # can release transactions on behalf of transactions_owner.
        prison = self.prisons[0]
        users = get_users_for_prison(prison)
        self.assertTrue(len(users) >= 2)

        logged_in_user = users[0]
        transactions_owner = users[1]

        pending_transactions = list(
            self._get_pending_transactions_qs(prison, transactions_owner)
        )

        # if this starts failing, we need to iterate over users and get the
        # first user with pending transactions.
        self.assertTrue(len(pending_transactions) > 0)

        # how many transactions should we release?
        to_release = random.randint(1, len(pending_transactions))
        transactions_to_release = pending_transactions[:to_release]

        currently_available = self._get_available_transactions_qs(prison).count()

        # request
        self.client.force_authenticate(user=logged_in_user)

        url = self._get_url(transactions_owner, prison)
        response = self.client.post(url, {
            'transaction_ids': [t.id for t in transactions_to_release]
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_303_SEE_OTHER)

        # check pending transactions == -to_release
        self.assertEqual(
            self._get_pending_transactions_qs(prison, transactions_owner).count(),
            len(pending_transactions) - to_release
        )

        # check that available transactions == +to_release
        self.assertEqual(
            self._get_available_transactions_qs(prison).count(),
            currently_available + to_release
        )

    def test_cannot_release_transactions_with_mismatched_url(self):
        """
        Tests that if we try to release all transactions_owner
        taken transactions + a logged_in_user transaction
        =>
        it fails
        """
        prison = self.prisons[0]
        users = get_users_for_prison(prison)
        self.assertTrue(len(users) >= 2)

        logged_in_user = users[0]
        transactions_owner = users[1]

        prison = get_prisons_for_user(transactions_owner)[0]

        pending_transactions_owner = list(
            self._get_pending_transactions_qs(prison, transactions_owner)
        )
        pending_transactions_logged_in = list(
            self._get_pending_transactions_qs(prison, logged_in_user)
        )

        # if this starts failing, we need to iterate over users and get the
        # first user with pending transactions.
        self.assertTrue(len(pending_transactions_owner) > 0)
        self.assertTrue(len(pending_transactions_logged_in) > 0)

        transactions_to_release = pending_transactions_owner + pending_transactions_logged_in[:1]

        self.client.force_authenticate(user=logged_in_user)

        url = self._get_url(transactions_owner, prison)
        response = self.client.post(url, {
            'transaction_ids': [t.id for t in transactions_to_release]
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # check nothing changed in the db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, transactions_owner).count(),
            len(pending_transactions_owner)
        )

        self.assertEqual(
            self._get_pending_transactions_qs(prison, logged_in_user).count(),
            len(pending_transactions_logged_in)
        )

    def test_cannot_release_credited_transactions(self):
        """
        Tests that if we tray to release all pending transactions +
        a credited transactions
        =>
        if fails
        """
        prison = self.prisons[0]
        users = get_users_for_prison(prison)
        self.assertTrue(len(users) >= 2)

        logged_in_user = users[0]
        transactions_owner = users[1]

        pending_transactions = list(
            self._get_pending_transactions_qs(prison, transactions_owner)
        )
        credited_transactions = list(
            self._get_credited_transactions_qs(transactions_owner, prison)
        )

        # if this starts failing, we need to iterate over users and get the
        # first user with pending transactions.
        self.assertTrue(len(pending_transactions) > 0)
        self.assertTrue(len(credited_transactions) > 0)

        transactions_to_release = pending_transactions + credited_transactions[:1]

        self.client.force_authenticate(user=logged_in_user)

        url = self._get_url(transactions_owner, prison)
        response = self.client.post(url, {
            'transaction_ids': [t.id for t in transactions_to_release]
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # check nothing changed in the db
        self.assertEqual(
            self._get_pending_transactions_qs(prison, transactions_owner).count(),
            len(pending_transactions)
        )

        self.assertEqual(
            self._get_credited_transactions_qs(logged_in_user, prison).count(),
            len(credited_transactions)
        )
