from credit.constants import CreditStatus
from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithDefaultPrisonTestCase(CreditListTestCase):
    def test_filter_by_status_credit_pending_and_user(self):
        """
        Returns available credits attached to all the prisons
        that the passed-in user can manage.
        """
        self._test_response_with_filters({
            'status': CreditStatus.credit_pending.value,
            'user': self.prison_clerks[1].pk,
        })

    def test_filter_by_status_credited_and_user(self):
        """
        Returns credits credited by the passed-in user.
        """
        self._test_response_with_filters({
            'status': CreditStatus.credited.value,
            'user': self.prison_clerks[1].pk,
        })
