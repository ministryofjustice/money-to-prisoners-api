import urllib.parse

from django.core.urlresolvers import reverse

from rest_framework import status

from mtp_auth.models import PrisonUserMapping

from prison.models import Prison

from transaction.models import Transaction
from transaction.constants import TRANSACTION_STATUS

from .test_base import BaseTransactionViewTestCase, \
    TransactionRejectsRequestsWithoutPermissionTestMixin


def get_prisons_for_user(user):
    return PrisonUserMapping.objects.get(user=user).prisons.all()


class CashbookTransactionRejectsRequestsWithoutPermissionTestMixin(
    TransactionRejectsRequestsWithoutPermissionTestMixin
):

    def _get_unauthorised_application_users(self):
        return [
            self.bank_admins[0], self.prisoner_location_admins[0]
        ]

    def _get_authorised_user(self):
        return self.prison_clerks[0]


class TransactionListTestCase(
    CashbookTransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):

    def _get_url(self, **filters):
        url = reverse('cashbook:transaction-prison-list')

        filters['limit'] = 1000
        return '{url}?{filters}'.format(
            url=url, filters=urllib.parse.urlencode(filters)
        )

    def _test_response_with_filters(self, filters={}):
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.add(*self.prisons)
        managing_prisons = list(get_prisons_for_user(logged_in_user))

        url = self._get_url(**filters)
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # check expected result
        status_checker = self.STATUS_FILTERS[filters.get('status', None)]
        if filters.get('prison'):
            prison_checker = lambda t: t.prison and t.prison.pk in filters['prison'].split(',')
        else:
            prison_checker = lambda t: True
        if filters.get('user'):
            user_checker = lambda t: t.owner and t.owner.pk == filters['user']
        else:
            user_checker = lambda t: True

        expected_ids = [
            t.pk for t in self.transactions if
                t.prison in managing_prisons and
                status_checker(t) and
                prison_checker(t) and
                user_checker(t)
        ]
        self.assertEqual(response.data['count'], len(expected_ids))
        self.assertListEqual(
            sorted([t['id'] for t in response.data['results']]),
            sorted(expected_ids)
        )

    def test_DEFAULT_status_AND_prison_AND_user(self):
        self._test_response_with_filters(filters={})

    def test_WITH_status_available_DEFAULT_prison_AND_user(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.AVAILABLE
        })

    def test_WITH_status_locked_DEFAULT_prison_AND_user(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.LOCKED
        })

    def test_WITH_status_credited_DEFAULT_prison_AND_user(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.CREDITED
        })

    def test_WITH_status_available_AND_prison_DEFAULT_user(self):
        self._test_response_with_filters(filters={
            'prison': self.prisons[0].pk
        })

    def test_WITH_status_locked_AND_prison_DEFAULT_user(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.LOCKED,
            'prison': self.prisons[0].pk
        })

    def test_WITH_status_credited_AND_prison_DEFAULT_user(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.CREDITED,
            'prison': self.prisons[0].pk
        })

    def test_WITH_status_available_AND_user_DEFAULT_prison(self):
        self._test_response_with_filters(filters={
            'user': self.prison_clerks[1].pk
        })

    def test_WITH_status_locked_AND_user_DEFAULT_prison(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.LOCKED,
            'user': self.prison_clerks[1].pk
        })

    def test_WITH_status_credited_AND_user_DEFAULT_prison(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.CREDITED,
            'user': self.prison_clerks[1].pk
        })

    def test_WITH_status_available_AND_prison_AND_user(self):
        self._test_response_with_filters(filters={
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })

    def test_WITH_status_locked_AND_prison_AND_user(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.LOCKED,
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })

    def test_WITH_status_credited_AND_prison_AND_user(self):
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.CREDITED,
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })

    def test_WITH_prison_DEFAULT_status_user(self):
        self._test_response_with_filters(filters={
            'prison': self.prisons[0].pk
        })

    def test_WITH_prison_AND_user_DEFAULT_status(self):
        self._test_response_with_filters(filters={
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })

    def test_WITH_user_DEFAULT_status_prison(self):
        self._test_response_with_filters(filters={
            'user': self.prison_clerks[1].pk
        })

    def test_invalid_status_filter(self):
        logged_in_user = self.prison_clerks[0]
        url = self._get_url(status='invalid')
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_invalid_user_filter(self):
        logged_in_user = self.prison_clerks[0]
        url = self._get_url(user='invalid')
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_invalid_prison_filter(self):
        logged_in_user = self.prison_clerks[0]
        url = self._get_url(prison='invalid')
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_prison_not_managed_by_loggedin_user(self):
        logged_in_user = self.prison_clerks[0]
        managing_prison_ids = get_prisons_for_user(logged_in_user).values_list('pk', flat=True)
        non_managing_prisons = Prison.objects.exclude(pk__in=managing_prison_ids)

        self.assertTrue(len(non_managing_prisons) > 0)

        url = self._get_url(prison=non_managing_prisons[0].pk)
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_prison_not_managed_by_passed_in_user(self):
        # logged-in user managing all the prisons
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.add(*self.prisons)

        # passed-in user managing only prison #1
        passed_in_user = self.prison_clerks[1]
        passed_in_user.prisonusermapping.prisons.clear()
        Transaction.objects.filter(
            owner=passed_in_user, prison__isnull=False
        ).update(prison=self.prisons[1])
        passed_in_user.prisonusermapping.prisons.add(self.prisons[1])

        # filtering by prison #0, passed-in user doesn't manage that one so it should
        # return an empty list
        url = self._get_url(
            user=passed_in_user.pk,
            prison=self.prisons[0].pk
        )
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_logged_in_user_not_managing_prison(self):
        # logged-in user managing only prison #1
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.clear()
        logged_in_user.prisonusermapping.prisons.add(self.prisons[1])

        # passed-in user managing all the prisons
        passed_in_user = self.prison_clerks[1]
        passed_in_user.prisonusermapping.prisons.add(*self.prisons)

        # filtering by prison #0, logged-in user doesn't manage that one so it should
        # return an empty list
        url = self._get_url(
            user=passed_in_user.pk,
            prison=self.prisons[0].pk
        )
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_multiple_prisons_passed_in(self):
        # logged-in user managing all the prisons
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.add(*self.prisons)
        managing_prisons = list(get_prisons_for_user(logged_in_user))

        url = self._get_url(**{
            'prison[]': [p.pk for p in self.prisons]
        })
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        expected_ids = [
            t.pk for t in self.transactions if
                t.prison in managing_prisons
        ]
        self.assertEqual(response.data['count'], len(expected_ids))
        self.assertListEqual(
            sorted([t['id'] for t in response.data['results']]),
            sorted(expected_ids)
        )
