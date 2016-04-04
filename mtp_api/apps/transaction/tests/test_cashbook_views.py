import datetime
import math
import random
from unittest import mock
import urllib.parse

from django.conf import settings
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.dateformat import format as format_date
from django.utils.timezone import localtime
from rest_framework import status

from mtp_auth.models import PrisonUserMapping
from prison.models import Prison
from transaction.api.cashbook.views import TransactionTextSearchFilter
from transaction.models import Transaction, Log
from transaction.constants import TRANSACTION_STATUS, LOCK_LIMIT, LOG_ACTIONS
from transaction.tests.test_base import BaseTransactionViewTestCase, \
    TransactionRejectsRequestsWithoutPermissionTestMixin
from transaction.tests.utils import generate_transactions


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
    pagination_response_keys = ['page', 'page_count']

    def _get_url(self, **filters):
        url = reverse('cashbook:transaction-list')

        filters['limit'] = 1000
        return '{url}?{filters}'.format(
            url=url, filters=urllib.parse.urlencode(filters)
        )

    def _get_managed_prison_transactions(self, logged_in_user=None):
        logged_in_user = logged_in_user or self._get_authorised_user()
        logged_in_user.prisonusermapping.prisons.add(*self.prisons)
        managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))
        return [t for t in self.transactions if t.prison in managing_prisons]

    def _test_response_with_filters(self, filters={}):
        logged_in_user = self._get_authorised_user()
        transactions = self._get_managed_prison_transactions()

        url = self._get_url(**filters)
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # check expected result
        def noop_checker(t):
            return True

        status_checker = self.STATUS_FILTERS[filters.get('status', None)]
        if filters.get('prison'):
            def prison_checker(t):
                return t.prison and t.prison.pk in filters['prison'].split(',')
        else:
            prison_checker = noop_checker
        if filters.get('user'):
            def user_checker(t):
                return t.owner and t.owner.pk == filters['user']
        else:
            user_checker = noop_checker
        received_at_checker = self._get_received_at_checker(filters, noop_checker)
        search_checker = self._get_search_checker(filters, noop_checker)

        expected_ids = [
            t.pk
            for t in transactions
            if status_checker(t) and
            prison_checker(t) and
            user_checker(t) and
            received_at_checker(t) and
            search_checker(t)
        ]
        self.assertEqual(response.data['count'], len(expected_ids))
        self.assertListEqual(
            sorted([t['id'] for t in response.data['results']]),
            sorted(expected_ids)
        )

        # ensure date-based pagination hasn't occurred
        for key in self.pagination_response_keys:
            self.assertNotIn(key, response.data)

        return response

    def _get_received_at_checker(self, filters, noop_checker):
        def parse_date(date):
            for date_format in settings.DATE_INPUT_FORMATS:
                try:
                    return datetime.datetime.strptime(date, date_format)
                except (ValueError, TypeError):
                    continue
            raise ValueError('Cannot parse date %s' % date)

        almost_one_day = datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)

        received_at_0, received_at_1 = filters.get('received_at_0'), filters.get('received_at_1')
        received_at_0 = parse_date(received_at_0) if received_at_0 else None
        received_at_1 = (parse_date(received_at_1) + almost_one_day) if received_at_1 else None

        received_at = filters.get('received_at')
        if received_at:
            if received_at_0 or received_at_1:
                raise NotImplementedError
            received_at = parse_date(received_at)
            received_at_0, received_at_1 = received_at, received_at + almost_one_day

        if received_at_0:
            received_at_0 = timezone.make_aware(received_at_0)
        if received_at_1:
            received_at_1 = timezone.make_aware(received_at_1)

        if received_at_0 and received_at_1:
            return lambda t: received_at_0 <= t.received_at <= received_at_1
        elif received_at_0:
            return lambda t: received_at_0 <= t.received_at
        elif received_at_1:
            return lambda t: t.received_at <= received_at_1
        return noop_checker

    def _get_search_checker(self, filters, noop_checker):
        if filters.get('search'):
            search_phrase = filters['search'].lower()
            search_fields = ['prisoner_name', 'prisoner_number', 'sender_name']

            return lambda t: any(
                search_phrase in getattr(t, field).lower()
                for field in search_fields
            ) or (search_phrase in '£%0.2f' % (t.amount / 100))
        return noop_checker


class TransactionListWithDefaultsTestCase(TransactionListTestCase):

    def test_returns_all_transactions(self):
        """
        Returns all transactions attached to all the prisons that
        the logged-in user can manage.
        """
        self._test_response_with_filters(filters={})


class TransactionListWithDefaultPrisonAndUserTestCase(TransactionListTestCase):

    def test_filter_by_status_available(self):
        """
        Returns available transactions attached to all the prisons
        that the logged-in user can manage.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.AVAILABLE
        })

    def test_filter_by_status_locked(self):
        """
        Returns locked transactions attached to all the prisons
        that the logged-in user can manage.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.LOCKED
        })

    def test_filter_by_status_credited(self):
        """
        Returns credited transactions attached to all the prisons
        that the logged-in user can manage.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.CREDITED
        })


class TransactionListWithDefaultUserTestCase(TransactionListTestCase):

    def test_filter_by_status_available_and_prison(self):
        """
        Returns available transactions attached to the passed-in prison.
        """
        self._test_response_with_filters(filters={
            'prison': self.prisons[0].pk
        })

    def test_filter_by_status_locked_and_prison(self):
        """
        Returns locked transactions attached to the passed-in prison.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.LOCKED,
            'prison': self.prisons[0].pk
        })

    def test_filter_by_status_credited_prison(self):
        """
        Returns crdited transactions attached to the passed-in prison.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.CREDITED,
            'prison': self.prisons[0].pk
        })


class TransactionListWithDefaultPrisonTestCase(TransactionListTestCase):

    def test_filter_by_status_available_and_user(self):
        """
        Returns available transactions attached to all the prisons
        that the passed-in user can manage.
        """
        self._test_response_with_filters(filters={
            'user': self.prison_clerks[1].pk
        })

    def test_filter_by_status_locked_and_user(self):
        """
        Returns transactions locked by the passed-in user.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.LOCKED,
            'user': self.prison_clerks[1].pk
        })

    def test_filter_by_status_credited_and_user(self):
        """
        Returns transactions credited by the passed-in user.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.CREDITED,
            'user': self.prison_clerks[1].pk
        })


class TransactionListWithoutDefaultsTestCase(TransactionListTestCase):

    def test_filter_by_status_available_and_prison_and_user(self):
        """
        Returns available transactions attached to the passed-in prison.
        """
        self._test_response_with_filters(filters={
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })

    def test_filter_by_status_locked_and_prison_and_user(self):
        """
        Returns transactions locked by the passed-in user and
        attached to the passed-in prison.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.LOCKED,
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })

    def test_filter_by_status_credited_and_prison_and_user(self):
        """
        Returns transactions credited by the passed-in user and
        attached to the passed-in prison.
        """
        self._test_response_with_filters(filters={
            'status': TRANSACTION_STATUS.CREDITED,
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })


class TransactionListWithDefaultStatusAndUserTestCase(TransactionListTestCase):

    def test_filter_by_prison(self):
        """
        Returns all transactions attached to the passed-in prison.
        """
        self._test_response_with_filters(filters={
            'prison': self.prisons[0].pk
        })

    def test_filter_by_multiple_prisons(self):
        """
        Returns all transactions attached to the passed-in prisons.
        """

        # logged-in user managing all the prisons
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.add(*self.prisons)
        managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))

        url = self._get_url(**{
            'prison[]': [p.pk for p in self.prisons]
        })
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        expected_ids = [
            t.pk
            for t in self.transactions
            if t.prison in managing_prisons
        ]
        self.assertEqual(response.data['count'], len(expected_ids))
        self.assertListEqual(
            sorted([t['id'] for t in response.data['results']]),
            sorted(expected_ids)
        )


class TransactionListWithDefaultStatusTestCase(TransactionListTestCase):

    def test_filter_by_prison_and_user(self):
        """
        Returns all transactions attached to the passed-in prison.
        """
        self._test_response_with_filters(filters={
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })


class TransactionListWithDefaultStatusAndPrisonTestCase(TransactionListTestCase):

    def test_filter_by_user(self):
        """
        Returns all transactions managed by the passed-in user
        """
        self._test_response_with_filters(filters={
            'user': self.prison_clerks[1].pk
        })


class TransactionListWithReceivedAtFilterTestCase(TransactionListTestCase):
    def _format_date(self, date):
        return format_date(date, 'Y-m-d')

    def test_filter_received_at_yesterday(self):
        """
        Returns all transactions received yesterday
        """
        yesterday = self._get_latest_date()
        self._test_response_with_filters(filters={
            'received_at_0': self._format_date(yesterday),
            'received_at_1': self._format_date(yesterday),
        })

    def test_filter_received_since_five_days_ago(self):
        """
        Returns all transactions received since 5 days ago
        """
        five_days_ago = self._get_latest_date() - datetime.timedelta(days=5)
        self._test_response_with_filters(filters={
            'received_at_0': self._format_date(five_days_ago),
        })

    def test_filter_received_until_five_days_ago(self):
        """
        Returns all transactions received until 5 days ago
        """
        five_days_ago = self._get_latest_date() - datetime.timedelta(days=5)
        self._test_response_with_filters(filters={
            'received_at_1': self._format_date(five_days_ago),
        })


class TransactionListWithSearchTestCase(TransactionListTestCase):
    def test_filter_search_for_prisoner_number(self):
        """
        Search for a prisoner number
        """
        while True:
            transaction = random.choice(self.transactions)
            if transaction.prisoner_number:
                break
        search_phrase = transaction.prisoner_number
        self._test_response_with_filters(filters={
            'search': search_phrase
        })

    def test_filter_search_for_prisoner_name(self):
        """
        Search for a prisoner first name
        """
        while True:
            transaction = random.choice(self.transactions)
            if transaction.prisoner_name:
                break
        search_phrase = transaction.prisoner_name.split()[0]
        self._test_response_with_filters(filters={
            'search': search_phrase
        })

    def test_filter_search_for_sender_name(self):
        """
        Search for a partial sender name
        """
        transaction = random.choice(self.transactions)
        search_phrase = transaction.sender_name[:2]
        self._test_response_with_filters(filters={
            'search': search_phrase
        })

    def test_filter_search_for_amount(self):
        """
        Search for a payment amount
        """
        transaction = random.choice(self.transactions)
        search_phrase = '£%0.2f' % (transaction.amount / 100)
        self._test_response_with_filters(filters={
            'search': search_phrase
        })

    def test_empty_search(self):
        """
        Empty search causes no errors
        """
        self._test_response_with_filters(filters={
            'search': ''
        })

    def test_search_with_no_results(self):
        """
        Search for a value that cannot exist in generated transactions
        """
        response = self._test_response_with_filters(filters={
            'search': get_random_string(
                length=20,  # too long for generated sender names
                allowed_chars='§±@£$#{}[];:<>',  # includes characters not used in generation
            )
        })
        self.assertFalse(response.data['results'])


class TransactionListInvalidValuesTestCase(TransactionListTestCase):

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
        managing_prison_ids = PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user)\
            .values_list('pk', flat=True)
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


class LockedTransactionListTestCase(TransactionListTestCase):
    def _get_url(self, **filters):
        url = reverse('cashbook:transaction-locked')

        filters['limit'] = 1000
        return '{url}?{filters}'.format(
            url=url, filters=urllib.parse.urlencode(filters)
        )

    def test_locked_transactions_returns_same_ones_as_filtered_list(self):
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.add(*self.prisons)
        # managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))

        url_list = super()._get_url(status=TRANSACTION_STATUS.LOCKED)
        response_list = self.client.get(
            url_list, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertTrue(response_list.data['count'])  # ensure some transactions exist!

        url_locked = self._get_url()
        response_locked = self.client.get(
            url_locked, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response_locked.status_code, status.HTTP_200_OK)
        self.assertEqual(response_locked.data['count'], response_list.data['count'])
        self.assertListEqual(
            list(sorted(transaction['id'] for transaction in response_locked.data['results'])),
            list(sorted(transaction['id'] for transaction in response_list.data['results'])),
        )
        self.assertTrue(all(transaction['locked'] for transaction in response_locked.data['results']))
        self.assertTrue(all('locked_at' in transaction for transaction in response_locked.data['results']))


class DateBasedPaginationTestCase(TransactionListTestCase):
    def _get_response(self, filters):
        logged_in_user = self._get_authorised_user()
        url = self._get_url(**filters)
        return self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

    def _test_invalid_response(self, filters):
        response = self._get_response(filters)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_ordering(self):
        self._test_invalid_response({'page_by_date_field': 'received_at',
                                     'ordering': 'prisoner_number'})

    def test_invalid_pagination(self):
        received_at_filter = self._get_random_transaction_date().strftime('%Y-%m-%d')
        self._test_invalid_response({'page_by_date_field': 'prisoner_name',
                                     'received_at': received_at_filter})

    def _get_random_transaction(self):
        return random.choice(self.transactions)

    def _get_date_of_transaction(self, transaction):
        return localtime(transaction.received_at).date()

    def _get_random_transaction_date(self):
        return self._get_date_of_transaction(self._get_random_transaction())

    def _get_date_count(self, transactions):
        transaction_dates = set(map(self._get_date_of_transaction, transactions))
        return len(transaction_dates)

    def _get_page_count(self, transactions, page_size=settings.REQUEST_PAGE_DAYS):
        return int(math.ceil(self._get_date_count(transactions) / page_size))

    def _get_all_pages_of_transactions(self, transactions, page_size=settings.REQUEST_PAGE_DAYS):
        all_pages = []
        current_page = []
        dates_collected = 0
        last_date = None
        for transaction in transactions:
            date = self._get_date_of_transaction(transaction)
            if date != last_date:
                dates_collected += 1
                last_date = date
            if dates_collected > page_size:
                dates_collected = 0
                last_date = date
                all_pages.append(current_page)
                current_page = []
            current_page.append(transaction)
        if current_page:
            all_pages.append(current_page)
        return all_pages

    def _get_page_of_transactions(self, transactions, page=1, page_size=settings.REQUEST_PAGE_DAYS):
        all_pages = self._get_all_pages_of_transactions(transactions, page_size=page_size)
        return all_pages[page - 1]

    def _get_page_of_transaction_ids(self, transactions, page=1, page_size=settings.REQUEST_PAGE_DAYS):
        page = self._get_page_of_transactions(transactions, page=page, page_size=page_size)
        return sorted(transaction.id for transaction in page)

    def _test_paginated_response(self, filters, transaction_ids, count, page, page_count):
        response = self._get_response(filters)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_ids = sorted(transaction['id'] for transaction in response.data['results'])
        self.assertListEqual(response_ids, transaction_ids)

        self.assertEqual(response.data['count'], count)
        self.assertEqual(response.data['page'], page)
        self.assertEqual(response.data['page_count'], page_count)

    def _get_transactions(self, transaction_filter=None, ordering='-received_at'):
        transactions = self._get_managed_prison_transactions()
        transactions = filter(transaction_filter, transactions)

        def transaction_sort(transaction):
            return transaction.received_at

        if ordering == 'received_at':
            transactions = sorted(transactions, key=transaction_sort)
        elif ordering == '-received_at':
            transactions = sorted(transactions, key=transaction_sort, reverse=True)
        else:
            raise NotImplementedError

        return transactions

    def test_pagination_without_filters(self):
        transactions = self._get_transactions()

        expected = {
            'count': len(transactions),
            'page': 1,
            'page_count': self._get_page_count(transactions),
            'transaction_ids': self._get_page_of_transaction_ids(transactions),
        }
        self._test_paginated_response(filters={'page_by_date_field': 'received_at',
                                               'ordering': '-received_at'},
                                      **expected)

    def test_pagination_with_search(self):
        search_term = ''
        while not search_term:
            random_transaction = self._get_random_transaction()
            search_term = random_transaction.prisoner_name or \
                random_transaction.prisoner_number
        search_term = search_term.lower().split()[0]

        search_fields = TransactionTextSearchFilter.fields

        def transaction_filter(transaction):
            return any(
                search_term in str(getattr(transaction, search_field, '') or '').lower()
                for search_field in search_fields
            )

        transactions = self._get_transactions(transaction_filter)

        expected = {
            'count': len(transactions),
            'page': 1,
            'page_count': self._get_page_count(transactions),
            'transaction_ids': self._get_page_of_transaction_ids(transactions),
        }
        self._test_paginated_response(filters={'page_by_date_field': 'received_at',
                                               'ordering': '-received_at',
                                               'search': search_term},
                                      **expected)

    def test_pagination_with_single_date(self):
        received_at = self._get_random_transaction_date()

        def transaction_filter(transaction):
            return self._get_date_of_transaction(transaction) == received_at

        transactions = self._get_transactions(transaction_filter)

        expected = {
            'count': len(transactions),
            'page': 1,
            'page_count': self._get_page_count(transactions),
            'transaction_ids': self._get_page_of_transaction_ids(transactions),
        }
        received_at_filter = received_at.strftime('%Y-%m-%d')
        self._test_paginated_response(filters={'page_by_date_field': 'received_at',
                                               'ordering': '-received_at',
                                               'received_at_0': received_at_filter,
                                               'received_at_1': received_at_filter},
                                      **expected)

    def test_pagination_with_date_range(self):
        received_at_0, received_at_1 = self._get_random_transaction_date(), self._get_random_transaction_date()
        if received_at_0 > received_at_1:
            received_at_0, received_at_1 = received_at_1, received_at_0

        def transaction_filter(transaction):
            return received_at_0 <= self._get_date_of_transaction(transaction) <= received_at_1

        transactions = self._get_transactions(transaction_filter)

        expected = {
            'count': len(transactions),
            'page': 1,
            'page_count': self._get_page_count(transactions),
            'transaction_ids': self._get_page_of_transaction_ids(transactions),
        }
        received_at_0_filter = received_at_0.strftime('%Y-%m-%d')
        received_at_1_filter = received_at_1.strftime('%Y-%m-%d')
        self._test_paginated_response(filters={'page_by_date_field': 'received_at',
                                               'ordering': '-received_at',
                                               'received_at_0': received_at_0_filter,
                                               'received_at_1': received_at_1_filter},
                                      **expected)

    def test_pagination_beyond_page_1(self):
        tries = 6
        page_count = 0
        transactions = []
        for _ in range(tries):
            transactions = self._get_transactions()
            page_count = self._get_page_count(transactions)
            if page_count > 1:
                break
            self.transactions = generate_transactions(
                transaction_batch=150
            )
        self.assertGreater(page_count, 1,
                           'Could not generate enough pages for test in %d tries' % tries)

        response = self._get_response(filters={'page_by_date_field': 'received_at',
                                               'ordering': '-received_at',
                                               'page': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        expected = {
            'count': len(transactions),
            'page': 2,
            'page_count': page_count,
            'transaction_ids': self._get_page_of_transaction_ids(transactions, page=2),
        }
        self._test_paginated_response(filters={'page_by_date_field': 'received_at',
                                               'ordering': '-received_at',
                                               'page': 2},
                                      **expected)


class LockTransactionTestCase(
    CashbookTransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):
    ENDPOINT_VERB = 'post'
    transaction_batch = 500

    def _get_url(self):
        return reverse('cashbook:transaction-lock')

    def setUp(self):
        super(LockTransactionTestCase, self).setUp()

        self.logged_in_user = self.prison_clerks[0]
        self.logged_in_user.prisonusermapping.prisons.add(*self.prisons)

    def _test_lock(self, already_locked_count, available_count=LOCK_LIMIT):
        locked_qs = self._get_locked_transactions_qs(self.prisons, self.logged_in_user)
        available_qs = self._get_available_transactions_qs(self.prisons)

        # set nr of transactions locked by logged-in user to 'already_locked'
        locked = locked_qs.values_list('pk', flat=True)
        Transaction.objects.filter(
            pk__in=[-1]+list(locked[:locked.count() - already_locked_count])
        ).delete()

        self.assertEqual(locked_qs.count(), already_locked_count)

        # set nr of transactions available to 'available'
        available = available_qs.values_list('pk', flat=True)
        Transaction.objects.filter(
            pk__in=[-1]+list(available[:available.count() - available_count])
        ).delete()

        self.assertEqual(available_qs.count(), available_count)

        expected_locked = min(
            already_locked_count + available_qs.count(),
            LOCK_LIMIT
        )

        # make lock request
        url = self._get_url()
        response = self.client.post(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_303_SEE_OTHER)

        # check that expected_locked got locked
        self.assertEqual(locked_qs.count(), expected_locked)

        return locked_qs

    def test_lock_with_none_locked_already(self):
        locked_transactions = self._test_lock(already_locked_count=0)

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=self.logged_in_user,
                action=LOG_ACTIONS.LOCKED,
                transaction__id__in=locked_transactions.values_list('id', flat=True)
            ).count(),
            locked_transactions.count()
        )

    def test_lock_with_max_locked_already(self):
        self._test_lock(already_locked_count=LOCK_LIMIT)

    def test_lock_with_some_locked_already(self):
        self._test_lock(already_locked_count=(LOCK_LIMIT/2))

    def test_lock_with_some_locked_already_but_none_available(self):
        self._test_lock(already_locked_count=(LOCK_LIMIT/2), available_count=0)


class UnlockTransactionTestCase(
    CashbookTransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):
    ENDPOINT_VERB = 'post'

    def _get_url(self):
        return reverse('cashbook:transaction-unlock')

    def test_can_unlock_somebody_else_s_transactions(self):
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.add(*self.prisons)
        locked_qs = self._get_locked_transactions_qs(self.prisons)

        to_unlock = list(locked_qs.values_list('id', flat=True))
        response = self.client.post(
            self._get_url(),
            {'transaction_ids': to_unlock},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_303_SEE_OTHER)
        self.assertEqual(
            urllib.parse.urlsplit(response['Location']).path,
            reverse('cashbook:transaction-list')
        )

        self.assertEqual(locked_qs.count(), 0)

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=logged_in_user,
                action=LOG_ACTIONS.UNLOCKED,
                transaction__id__in=to_unlock
            ).count(),
            len(to_unlock)
        )

    def test_cannot_unlock_somebody_else_s_transactions_in_different_prison(self):
        # logged-in user managing prison #0
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.clear()
        logged_in_user.prisonusermapping.prisons.add(self.prisons[0])

        # other user managing prison #1
        other_user = self.prison_clerks[1]
        other_user.prisonusermapping.prisons.add(self.prisons[1])

        locked_qs = self._get_locked_transactions_qs(self.prisons, other_user)
        locked_qs.update(prison=self.prisons[1])

        to_unlock = locked_qs.values_list('id', flat=True)
        response = self.client.post(
            self._get_url(),
            {'transaction_ids': to_unlock},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        errors = response.data['errors']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['msg'], 'Some transactions could not be unlocked.')
        self.assertEqual(errors[0]['ids'], sorted(to_unlock))

    def test_cannot_unlock_credited_transactions(self):
        logged_in_user = self.prison_clerks[0]
        managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))

        locked_qs = self._get_locked_transactions_qs(managing_prisons, user=logged_in_user)
        credited_qs = self._get_credited_transactions_qs(managing_prisons, user=logged_in_user)

        locked_ids = list(locked_qs.values_list('id', flat=True))
        credited_ids = list(credited_qs.values_list('id', flat=True)[:1])

        response = self.client.post(
            self._get_url(),
            {'transaction_ids': locked_ids + credited_ids},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        errors = response.data['errors']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['msg'], 'Some transactions could not be unlocked.')
        self.assertEqual(errors[0]['ids'], sorted(credited_ids))

    @mock.patch('transaction.api.cashbook.views.transaction_prisons_need_updating')
    def test_unlock_sends_transaction_prisons_need_updating_signal(
        self, mocked_transaction_prisons_need_updating
    ):
        logged_in_user = self.prison_clerks[0]
        logged_in_user.prisonusermapping.prisons.add(*self.prisons)
        locked_qs = self._get_locked_transactions_qs(self.prisons)

        response = self.client.post(
            self._get_url(),
            {'transaction_ids': list(locked_qs.values_list('id', flat=True))},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_303_SEE_OTHER)

        mocked_transaction_prisons_need_updating.send.assert_called_with(sender=Transaction)


class CreditTransactionTestCase(
    CashbookTransactionRejectsRequestsWithoutPermissionTestMixin,
    BaseTransactionViewTestCase
):
    ENDPOINT_VERB = 'patch'

    def _get_url(self, **filters):
        return reverse('cashbook:transaction-list')

    def test_credit_uncredit_transactions(self):
        logged_in_user = self.prison_clerks[0]
        managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))

        locked_qs = self._get_locked_transactions_qs(managing_prisons, logged_in_user)
        credited_qs = self._get_credited_transactions_qs(managing_prisons, logged_in_user)

        self.assertTrue(locked_qs.count() > 0)
        self.assertTrue(credited_qs.count() > 0)

        to_credit = list(locked_qs.values_list('id', flat=True))
        to_uncredit = list(credited_qs.values_list('id', flat=True))

        data = [
            {'id': t_id, 'credited': True} for t_id in to_credit
        ] + [
            {'id': t_id, 'credited': False} for t_id in to_uncredit
        ]

        response = self.client.patch(
            self._get_url(), data=data,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # check db
        self.assertEqual(
            credited_qs.filter(id__in=to_credit).count(), len(to_credit)
        )
        self.assertEqual(
            locked_qs.filter(id__in=to_uncredit).count(), len(to_uncredit)
        )

        # check logs
        self.assertEqual(
            Log.objects.filter(
                user=logged_in_user,
                action=LOG_ACTIONS.CREDITED,
                transaction__id__in=to_credit
            ).count(),
            len(to_credit)
        )

        self.assertEqual(
            Log.objects.filter(
                user=logged_in_user,
                action=LOG_ACTIONS.UNCREDITED,
                transaction__id__in=to_uncredit
            ).count(),
            len(to_uncredit)
        )

    def test_cannot_credit_somebody_else_s_transactions(self):
        logged_in_user = self.prison_clerks[0]
        other_user = self.prison_clerks[1]

        locked_qs = self._get_locked_transactions_qs(self.prisons, logged_in_user)
        credited_qs = self._get_credited_transactions_qs(self.prisons, logged_in_user)
        locked_by_other_user_qs = self._get_locked_transactions_qs(self.prisons, other_user)

        credited = credited_qs.count()

        locked_by_other_user_ids = list(locked_by_other_user_qs.values_list('id', flat=True))
        data = [
            {'id': t_id, 'credited': True}
            for t_id in locked_qs.values_list('id', flat=True)
        ] + [
            {'id': t_id, 'credited': True}
            for t_id in locked_by_other_user_ids
        ]

        response = self.client.patch(
            self._get_url(), data=data,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        errors = response.data['errors']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['msg'], 'Some transactions could not be credited.')
        self.assertEqual(errors[0]['ids'], sorted(locked_by_other_user_ids))

        # nothing changed in db
        self.assertEqual(credited_qs.count(), credited)

    def test_cannot_credit_non_locked_transactions(self):
        logged_in_user = self.prison_clerks[0]
        managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))

        locked_qs = self._get_locked_transactions_qs(managing_prisons, logged_in_user)
        credited_qs = self._get_credited_transactions_qs(self.prisons, logged_in_user)
        available_qs = self._get_available_transactions_qs(managing_prisons)

        credited = credited_qs.count()

        available_ids = available_qs.values_list('id', flat=True)
        data = [
            {'id': t_id, 'credited': True}
            for t_id in locked_qs.values_list('id', flat=True)
        ] + [
            {'id': t_id, 'credited': True}
            for t_id in available_ids
        ]

        response = self.client.patch(
            self._get_url(), data=data,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        errors = response.data['errors']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['msg'], 'Some transactions could not be credited.')
        self.assertEqual(errors[0]['ids'], sorted(available_ids))

        # nothing changed in db
        self.assertEqual(credited_qs.count(), credited)

    def test_invalid_format(self):
        logged_in_user = self.prison_clerks[0]

        response = self.client.patch(
            self._get_url(), data={},
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_ids(self):
        logged_in_user = self.prison_clerks[0]

        response = self.client.patch(
            self._get_url(), data=[
                {'credited': True}
            ],
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_misspelt_credit(self):
        logged_in_user = self.prison_clerks[0]
        managing_prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(logged_in_user))

        locked_qs = self._get_locked_transactions_qs(managing_prisons, logged_in_user)

        data = [
            {'id': t_id, 'credted': True}
            for t_id in locked_qs.values_list('id', flat=True)
        ]

        response = self.client.patch(
            self._get_url(), data=data,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
