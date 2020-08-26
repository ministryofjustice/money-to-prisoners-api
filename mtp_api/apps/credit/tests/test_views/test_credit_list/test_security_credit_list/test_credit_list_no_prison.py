from credit.tests.test_views.test_credit_list.test_security_credit_list import SecurityCreditListTestCase


class NoPrisonCreditListTestCase(SecurityCreditListTestCase):
    def test_no_prison_filter(self):
        self._test_response_with_filters({
            'prison__isnull': 'True'
        })
