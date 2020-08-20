from credit.models import Credit
from credit.tests.test_views.test_credit_list.test_security_credit_list import SecurityCreditListTestCase


class TransactionSenderDetailsCreditListTestCase(SecurityCreditListTestCase):
    def test_sort_code_filter(self):
        random_sort_code = (
            Credit.objects.filter(transaction__sender_sort_code__isnull=False)
            .exclude(transaction__sender_sort_code='')
            .order_by('?').first().sender_sort_code
        )
        self._test_response_with_filters({
            'sender_sort_code': random_sort_code
        })

    def test_account_number_filter(self):
        random_account_number = (
            Credit.objects.filter(transaction__sender_account_number__isnull=False)
            .exclude(transaction__sender_account_number='')
            .order_by('?').first().sender_account_number
        )
        self._test_response_with_filters({
            'sender_account_number': random_account_number
        })

    def test_roll_number_filter(self):
        random_roll_number = (
            Credit.objects.filter(transaction__sender_roll_number__isnull=False)
            .exclude(transaction__sender_roll_number='')
            .order_by('?').first().sender_roll_number
        )
        self._test_response_with_filters({
            'sender_roll_number': random_roll_number
        })
