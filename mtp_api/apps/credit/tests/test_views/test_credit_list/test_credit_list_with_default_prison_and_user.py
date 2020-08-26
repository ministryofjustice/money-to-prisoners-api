from credit.constants import CREDIT_STATUS
from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithDefaultPrisonAndUserTestCase(CreditListTestCase):
    def test_filter_by_status_credit_pending(self):
        """
        Returns available credits attached to all the prisons
        that the logged-in user can manage.
        """
        self._test_response_with_filters({
            'status': CREDIT_STATUS.CREDIT_PENDING
        })

    def test_filter_by_status_credited(self):
        """
        Returns credited credits attached to all the prisons
        that the logged-in user can manage.
        """
        self._test_response_with_filters({
            'status': CREDIT_STATUS.CREDITED
        })
