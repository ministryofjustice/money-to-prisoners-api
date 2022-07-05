from credit.models import Credit
from credit.tests.test_views.test_credit_list import CreditListTestCase


class SecurityCreditListTestCase(CreditListTestCase):
    def _get_authorised_user(self):
        return self.security_staff[0]

    def _test_response_with_filters(self, filters):
        response = super()._test_response_with_filters(filters)
        for response_credit in response.data['results']:
            db_credit = Credit.objects.get(pk=response_credit['id'])
            self.assertEqual(
                db_credit.sender_sort_code,
                response_credit.get('sender_sort_code')
            )
            self.assertEqual(
                db_credit.sender_account_number,
                response_credit.get('sender_account_number')
            )
            self.assertEqual(
                db_credit.sender_roll_number,
                response_credit.get('sender_roll_number')
            )
