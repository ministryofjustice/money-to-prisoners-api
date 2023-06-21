from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithDefaultStatusAndPrisonTestCase(CreditListTestCase):
    def test_filter_by_user(self):
        """
        Returns all credits managed by the passed-in user
        """
        self._test_response_with_filters({
            'user': self.prison_clerks[1].pk,
        })
