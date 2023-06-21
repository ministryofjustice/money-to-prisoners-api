from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithDefaultStatusTestCase(CreditListTestCase):
    def test_filter_by_prison_and_user(self):
        """
        Returns all credits attached to the passed-in prison.
        """
        self._test_response_with_filters({
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk,
        })
