from core import getattr_path
from rest_framework import status

from credit.tests.test_views.test_credit_list.test_security_credit_list import SecurityCreditListTestCase


class CreditListWithBlankStringFiltersTestCase(SecurityCreditListTestCase):
    def assertAllResponsesHaveBlankField(self, filters, blank_fields, expected_filter):  # noqa: N802
        expected_results = list(filter(expected_filter, self._get_managed_prison_credits()))

        url = self._get_url(**filters)
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self._get_authorised_user())
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = []
        for result in response.data.get('results', []):
            results.append(result['id'])
            for blank_field in blank_fields:
                self.assertIn(result[blank_field], ['', None])

        self.assertListEqual(
            sorted(results),
            sorted(expected_result.id for expected_result in expected_results)
        )

    def test_blank_sender_name(self):
        self.assertAllResponsesHaveBlankField(
            {
                'sender_name__isblank': 'True'
            },
            ['sender_name'],
            lambda credit: getattr_path(credit, 'transaction.sender_name', None) == ''
        )

    def test_blank_sender_sort_code(self):
        self.assertAllResponsesHaveBlankField(
            {
                'sender_sort_code__isblank': 'True'
            },
            ['sender_sort_code'],
            lambda credit: getattr_path(credit, 'transaction.sender_sort_code', None) == ''
        )

    def test_blank_sender_account_number(self):
        self.assertAllResponsesHaveBlankField(
            {
                'sender_account_number__isblank': 'True'
            },
            ['sender_account_number'],
            lambda credit: getattr_path(credit, 'transaction.sender_account_number', None) == ''
        )

    def test_blank_sender_roll_number(self):
        self.assertAllResponsesHaveBlankField(
            {
                'sender_roll_number__isblank': 'True'
            },
            ['sender_roll_number'],
            lambda credit: getattr_path(credit, 'transaction.sender_roll_number', None) == ''
        )
