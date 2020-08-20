import random

from credit.tests.test_views.test_credit_list.test_security_credit_list import SecurityCreditListTestCase


class AmountPatternCreditListTestCase(SecurityCreditListTestCase):
    def test_exclude_amount_pattern_filter_endswith_multiple(self):
        self._test_response_with_filters({
            'exclude_amount__endswith': ['000', '500'],
        })

    def test_exclude_amount_pattern_filter_regex(self):
        self._test_response_with_filters({
            'exclude_amount__regex': '^.*000$',
        })

    def test_amount_pattern_filter_endswith(self):
        self._test_response_with_filters({
            'amount__endswith': '000',
        })

    def test_amount_pattern_filter_endswith_multiple(self):
        self._test_response_with_filters({
            'amount__endswith': ['000', '500'],
        })

    def test_amount_pattern_filter_regex(self):
        self._test_response_with_filters({
            'amount__regex': '^.*000$',
        })

    def test_amount_pattern_filter_less_than_regex(self):
        self._test_response_with_filters({
            'amount__lte': 5000,
            'amount__regex': '^.*00$',
        })

    def test_amount_pattern_filter_range(self):
        self._test_response_with_filters({
            'amount__gte': 5000,
            'amount__lte': 10000,
        })

    def test_amount_pattern_filter_exact(self):
        random_amount = random.choice(self.credits).amount
        self._test_response_with_filters({
            'amount': random_amount,
        })
