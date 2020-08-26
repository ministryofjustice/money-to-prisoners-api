from credit.constants import CREDIT_STATUS
from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithoutDefaultsTestCase(CreditListTestCase):
    def test_filter_by_status_credit_pending_and_prison_and_user(self):
        """
        Returns available credits attached to the passed-in prison.
        """
        self._test_response_with_filters({
            'status': CREDIT_STATUS.CREDIT_PENDING,
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })

    def test_filter_by_status_credited_and_prison_and_user(self):
        """
        Returns credits credited by the passed-in user and
        attached to the passed-in prison.
        """
        self._test_response_with_filters({
            'status': CREDIT_STATUS.CREDITED,
            'prison': self.prisons[0].pk,
            'user': self.prison_clerks[1].pk
        })
