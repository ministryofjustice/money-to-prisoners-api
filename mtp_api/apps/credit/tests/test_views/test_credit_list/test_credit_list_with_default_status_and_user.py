from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithDefaultStatusAndUserTestCase(CreditListTestCase):
    def test_filter_by_prison(self):
        """
        Returns all credits attached to the passed-in prison.
        """
        self._test_response_with_filters({
            'prison': self.prisons[0].pk
        })

    def test_filter_by_multiple_prisons(self):
        """
        Returns all credits attached to the passed-in prisons.
        """
        self._test_response_with_filters({
            'prison[]': [p.pk for p in self.prisons]
        })
