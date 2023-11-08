import logging

from django.core.management import call_command
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from disbursement.tests.utils import generate_disbursements
from mtp_auth.tests.utils import AuthTestCaseMixin
from mtp_common.test_utils import silence_logger
from payment.tests.utils import generate_payments
from prison.tests.utils import load_random_prisoner_locations
from transaction.tests.utils import generate_transactions


class SecurityViewTestCase(APITestCase, AuthTestCaseMixin):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    @silence_logger(level=logging.ERROR)
    def setUp(self):
        super().setUp()
        self.test_users = make_test_users()
        self.prison_clerks = self.test_users['prison_clerks']
        self.security_staff = self.test_users['security_staff']
        load_random_prisoner_locations()
        generate_transactions(transaction_batch=100, days_of_history=5)
        generate_payments(payment_batch=100, days_of_history=5)
        generate_disbursements(disbursement_batch=150, days_of_history=5)
        call_command('update_security_profiles')

    def _get_unauthorised_application_users(self):
        return self.prison_clerks

    def _get_url(self, *args, **kwargs):
        raise NotImplementedError

    def _get_authorised_user(self):
        return self.security_staff[0]

    def _get_list(self, user, path_params=(), **filters):
        url = self._get_url(*path_params)

        if 'limit' not in filters:
            filters['limit'] = 1000
        response = self.client.get(
            url, filters, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        return response.data
