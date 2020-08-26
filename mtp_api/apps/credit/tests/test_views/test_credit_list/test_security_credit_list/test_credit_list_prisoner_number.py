from credit.models import Credit
from credit.tests.test_views.test_credit_list.test_security_credit_list import SecurityCreditListTestCase


class PrisonerNumberCreditListTestCase(SecurityCreditListTestCase):
    def test_prisoner_number_filter(self):
        random_prisoner_number = (
            Credit.objects.filter(prisoner_number__isnull=False)
            .exclude(prisoner_number='')
            .order_by('?').first().prisoner_number
        )
        self._test_response_with_filters({
            'prisoner_number': random_prisoner_number
        })
