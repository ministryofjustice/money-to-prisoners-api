from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithValidFilterTestCase(CreditListTestCase):
    def test_filter_by_invalidity(self):
        self._test_response_with_filters({
            'valid': 'true'
        })

    def test_filter_by_validity(self):
        self._test_response_with_filters({
            'valid': 'false'
        })
