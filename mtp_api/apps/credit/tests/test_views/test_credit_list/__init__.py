import datetime
import re
import urllib.parse

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status

from core import getattr_path
from credit.constants import (
    CREDIT_STATUS, CREDIT_RESOLUTION
)
from credit.tests.test_base import (
    BaseCreditViewTestCase, CreditRejectsRequestsWithoutPermissionTestMixin
)


class CashbookCreditRejectsRequestsWithoutPermissionTestMixin(
    CreditRejectsRequestsWithoutPermissionTestMixin
):
    def _get_unauthorised_application_users(self):
        return self.send_money_users

    def _get_authorised_user(self):
        return self.prison_clerks[0]


class CreditListTestCase(
    CashbookCreditRejectsRequestsWithoutPermissionTestMixin,
    BaseCreditViewTestCase
):
    pagination_response_keys = ['page', 'page_count']

    def _get_url(self, **filters):
        url = reverse('credit-list')

        filters['limit'] = 1000
        return '{url}?{filters}'.format(
            url=url, filters=urllib.parse.urlencode(filters, doseq=True)
        )

    def _get_invalid_credits(self):
        return [c for c in self.credits if c.prison is None]

    def _test_response(self, filters):
        logged_in_user = self._get_authorised_user()
        url = self._get_url(**filters)
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        return response

    def _test_response_with_filters(self, filters):
        credits = self._get_managed_prison_credits()
        response = self._test_response(filters)

        # check expected result
        def noop_checker(c):
            return True

        status_checker = self.STATUS_FILTERS[filters.get('status', None)]
        if filters.get('prison'):
            def prison_checker(c):
                return c.prison and c.prison.pk in filters['prison'].split(',')
        elif filters.get('prison__isnull'):
            def prison_checker(c):
                return (c.prison is None) == (filters['prison__isnull'] == 'True')
        else:
            prison_checker = noop_checker
        if filters.get('user'):
            def user_checker(c):
                return c.owner and c.owner.pk == filters['user']
        else:
            user_checker = noop_checker
        received_at_checker = self._get_received_at_checker(filters, noop_checker)
        search_checker = self._get_search_checker(filters, noop_checker)
        sender_name_checker = self._get_attribute_checker(
            'sender_name', filters, noop_checker, True
        )
        sender_sort_code_checker = self._get_attribute_checker(
            'sender_sort_code', filters, noop_checker
        )
        sender_account_number_checker = self._get_attribute_checker(
            'sender_account_number', filters, noop_checker
        )
        sender_roll_number_checker = self._get_attribute_checker(
            'sender_roll_number', filters, noop_checker
        )
        prisoner_name_checker = self._get_attribute_checker(
            'prisoner_name', filters, noop_checker, True
        )
        prisoner_number_checker = self._get_attribute_checker(
            'prisoner_number', filters, noop_checker
        )
        prison_region_checker = self._get_sub_attribute_checker(
            'prison_region', 'prison.region', filters, noop_checker
        )
        prison_population_checker = self._get_prison_type_checker(
            'prison_population', 'prison.populations', filters, noop_checker
        )
        prison_category_checker = self._get_prison_type_checker(
            'prison_category', 'prison.categories', filters, noop_checker
        )
        amount_pattern_checker = self._get_amount_pattern_checker(filters, noop_checker)
        valid_checker = self._get_valid_checker(filters, noop_checker)
        pk_checker = self._get_primary_key_checker(filters, noop_checker)

        expected_ids = [
            c.pk
            for c in credits
            if c.resolution not in (
                CREDIT_RESOLUTION.INITIAL,
                CREDIT_RESOLUTION.FAILED,
            ) and
            status_checker(c) and
            prison_checker(c) and
            user_checker(c) and
            received_at_checker(c) and
            search_checker(c) and
            sender_name_checker(c) and
            sender_sort_code_checker(c) and
            sender_account_number_checker(c) and
            sender_roll_number_checker(c) and
            prisoner_name_checker(c) and
            prisoner_number_checker(c) and
            prison_region_checker(c) and
            prison_population_checker(c) and
            prison_category_checker(c) and
            amount_pattern_checker(c) and
            valid_checker(c) and
            pk_checker(c)
        ]

        self.assertEqual(response.data['count'], len(expected_ids))
        self.assertListEqual(
            sorted([c['id'] for c in response.data['results']]),
            sorted(expected_ids)
        )

        # ensure date-based pagination hasn't occurred
        for key in self.pagination_response_keys:
            self.assertNotIn(key, response.data)

        return response

    def _get_attribute_checker(self, attribute, filters, noop_checker, text_search=False):
        if filters.get(attribute):
            if text_search:
                return lambda c: filters[attribute].lower() in (getattr(c, attribute) or '').lower()
            return lambda c: getattr(c, attribute) == filters[attribute]
        return noop_checker

    def _get_multivalue_attribute_checker(self, attribute, filters, noop_checker, text_search=False):
        if filters.get(attribute):
            return lambda c: getattr(c, attribute) in filters[attribute]
        return noop_checker

    def _get_sub_attribute_checker(self, filter_name, attribute_path, filters, noop_checker, text_search=False):
        if filters.get(filter_name):
            if text_search:
                return lambda c: filters[filter_name].lower() in getattr_path(c, attribute_path, '').lower()
            return lambda c: getattr_path(c, attribute_path) == filters[filter_name]
        return noop_checker

    def _get_primary_key_checker(self, filters, noop_checker, text_search=False):
        if 'exclude_credit__in' in filters:
            excluded_pks = filters['exclude_credit__in']
            if type(excluded_pks) is not list:
                excluded_pks = [excluded_pks]
            return lambda c: c.id not in excluded_pks
        return self._get_multivalue_attribute_checker('pk', filters, noop_checker, text_search)

    def _get_prison_type_checker(self, filter_name, list_attribute_path, filters, noop_checker):
        if filters.get(filter_name):
            filter_list = filters[filter_name] if isinstance(filters[filter_name], list) else [filters[filter_name]]
            return lambda c: any(
                value in [t.name for t in getattr_path(c, list_attribute_path).all()]
                for value in filter_list
            )
        return noop_checker

    def _get_received_at_checker(self, filters, noop_checker):
        def parse_date(date):
            parsed_date = parse_datetime(date)
            if parsed_date is not None:
                return parsed_date
            for date_format in settings.DATETIME_INPUT_FORMATS:
                try:
                    return datetime.datetime.strptime(date, date_format)
                except (ValueError, TypeError):
                    continue
            raise ValueError('Cannot parse date', {'date': date})

        received_at__gte, received_at__lt = filters.get('received_at__gte'), filters.get('received_at__lt')
        received_at__gte = parse_date(received_at__gte) if received_at__gte else None
        received_at__lt = parse_date(received_at__lt) if received_at__lt else None

        if received_at__gte and received_at__gte.tzinfo is None:
            received_at__gte = timezone.make_aware(received_at__gte)
        if received_at__lt and received_at__lt.tzinfo is None:
            received_at__lt = timezone.make_aware(received_at__lt)

        if received_at__gte and received_at__lt:
            return lambda c: received_at__gte <= c.received_at < received_at__lt
        elif received_at__gte:
            return lambda c: received_at__gte <= c.received_at
        elif received_at__lt:
            return lambda c: c.received_at < received_at__lt
        return noop_checker

    def _get_search_checker(self, filters, noop_checker):
        if filters.get('search'):
            search_phrase = filters['search'].lower()
            search_fields = ['prisoner_name', 'prisoner_number', 'sender_name']

            return lambda c: any(
                search_phrase in (getattr(c, field) or '').lower()
                for field in search_fields
            ) or (search_phrase in '£%0.2f' % (c.amount / 100))
        return noop_checker

    def _get_amount_pattern_checker(self, filters, noop_checker):
        checkers = [noop_checker]
        if 'exclude_amount__endswith' in filters:
            excluded_ends = filters['exclude_amount__endswith']
            if type(excluded_ends) is not list:
                excluded_ends = [excluded_ends]
            for ending in excluded_ends:
                checkers.append(
                    lambda c: not str(c.amount).endswith(ending)
                )
        if 'exclude_amount__regex' in filters:
            checkers.append(lambda c: not re.match(
                filters['exclude_amount__regex'], str(c.amount))
            )
        if 'amount__endswith' in filters:
            endings = filters['amount__endswith']
            if type(endings) is not list:
                endings = [endings]
            for ending in endings:
                checkers.append(
                    lambda c: str(c.amount).endswith(ending)
                )
        if 'amount__regex' in filters:
            checkers.append(lambda c: re.match(
                filters['amount__regex'], str(c.amount))
            )
        if 'amount__lte' in filters:
            checkers.append(lambda c: c.amount <= int(filters['amount__lte']))
        if 'amount__gte' in filters:
            checkers.append(lambda c: c.amount >= int(filters['amount__gte']))
        if 'amount' in filters:
            checkers.append(lambda c: c.amount == int(filters['amount']))
        return lambda c: all([checker(c) for checker in checkers])

    def _get_valid_checker(self, filters, noop_checker):
        if 'valid' in filters:
            def valid_checker(c):
                return (
                    self.STATUS_FILTERS[CREDIT_STATUS.CREDIT_PENDING](c) or
                    self.STATUS_FILTERS[CREDIT_STATUS.CREDITED](c)
                )
            if filters['valid'] in ('true', 'True', 1, True):
                return valid_checker
            else:
                return lambda c: not valid_checker(c)
        return noop_checker
