from django.utils.crypto import get_random_string
from rest_framework import status

from credit.models import Credit
from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithSimpleSearchTestCase(CreditListTestCase):
    def test_search(self):
        """
        Test for when the search param `simple_search` is used.

        Checks that the API return the credits with the supplied search value in
            the sender name of a transaction object
            OR
            the cardholder name of a payment object
            OR
            the email address of a payment object
            OR
            the prisoner number
        """
        # prepare the data
        managed_prison_credits = self._get_managed_prison_credits()
        managed_prison_credits_ids = [credit.id for credit in managed_prison_credits]

        # change the loaded data so that the test matches exactly 3 records
        term_part1 = get_random_string(10)
        term_part2 = get_random_string(10)
        term = f'{term_part1} {term_part2}'

        credit_with_transaction = Credit.objects.filter(
            transaction__isnull=False,
            payment__isnull=True,
            id__in=managed_prison_credits_ids,
        ).order_by('?').first()
        credit_with_transaction.transaction.sender_name = f'{term}Junior'.upper()
        credit_with_transaction.transaction.save()

        credits_with_payment = list(
            Credit.objects.filter(
                transaction__isnull=True,
                payment__isnull=False,
                id__in=managed_prison_credits_ids,
            ).order_by('?')[:3]
        )
        credits_with_payment[0].payment.cardholder_name = f'Mr{term_part1}an {term_part2}'
        credits_with_payment[0].payment.save()

        credits_with_payment[1].prisoner_number = term_part1
        credits_with_payment[1].payment.email = f'{term_part2}@example.com'
        credits_with_payment[1].save()
        credits_with_payment[1].payment.save()

        # this should not be matched as only term_part1 is present
        credits_with_payment[2].prisoner_number = term_part1
        credits_with_payment[2].save()

        # run the test
        logged_in_user = self._get_authorised_user()

        url = self._get_url(
            **{
                'simple_search': term,
            },
        )
        response = self.client.get(
            url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(logged_in_user),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.data['results']
        self.assertEqual(len(response_data), 3)
        self.assertEqual(
            {item['id'] for item in response_data},
            {
                credit_with_transaction.id,
                credits_with_payment[0].id,
                credits_with_payment[1].id,
            },
        )
