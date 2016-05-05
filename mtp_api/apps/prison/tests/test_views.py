import random
from unittest import mock

from django.core.urlresolvers import reverse
from django.utils.dateformat import format as format_date
from model_mommy import mommy
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin
from mtp_auth.constants import CASHBOOK_OAUTH_CLIENT_ID
from prison.models import Prison, PrisonerLocation
from prison.tests.utils import random_prisoner_name, random_prisoner_number, random_prisoner_dob
from transaction.tests.utils import generate_transactions


class PrisonerLocationViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super(PrisonerLocationViewTestCase, self).setUp()
        (self.prison_clerks, self.users,
         self.bank_admins, self.refund_bank_admins,
         self.send_money_users) = make_test_users()
        self.prisons = Prison.objects.all()

    @property
    def list_url(self):
        return reverse('prisonerlocation-list')

    def test_fails_without_application_permissions(self):
        """
        Tests that if the user logs in via a different application,
        they won't be able to access the API.
        """
        users_data = [
            (
                self.prison_clerks[0],
                self.get_http_authorization_for_user(self.prison_clerks[0])
            ),
            (
                self.bank_admins[0],
                self.get_http_authorization_for_user(self.bank_admins[0])
            ),
            (
                self.refund_bank_admins[0],
                self.get_http_authorization_for_user(self.refund_bank_admins[0])
            ),
            (
                self.users[0],
                self.get_http_authorization_for_user(self.users[0], client_id=CASHBOOK_OAUTH_CLIENT_ID)
            ),
            (
                self.send_money_users[0],
                self.get_http_authorization_for_user(self.send_money_users[0])
            ),
        ]

        for user, http_auth_header in users_data:
            response = self.client.post(
                self.list_url, data={}, format='json',
                HTTP_AUTHORIZATION=http_auth_header
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                             'for user %s' % user)

    def test_fails_without_action_permissions(self):
        """
        Tests that if the user does not have permissions to create
        transactions, they won't be able to access the API.
        """
        unauthorised_user = self.users[0]

        unauthorised_user.groups.first().permissions.all().delete()

        response = self.client.post(
            self.list_url, data={}, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(unauthorised_user)
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

    def test_cannot_create_if_not_logged_in(self):
        response = self.client.post(
            self.list_url, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create(self):
        user = self.users[0]

        repeated_p_num_1 = random_prisoner_number()
        repeated_p_num_2 = random_prisoner_number()
        # create two pre-existing PrisonerLocations so that we test the overwrite
        mommy.make(PrisonerLocation, prisoner_number=repeated_p_num_1,
                   prison=self.prisons[0])
        mommy.make(PrisonerLocation, prisoner_number=repeated_p_num_2,
                   prison=self.prisons[0])
        self.assertEqual(PrisonerLocation.objects.count(), 2)

        data = [
            {
                'prisoner_name': random_prisoner_name(),
                'prisoner_number': random_prisoner_number(),
                'prisoner_dob': random_prisoner_dob(),
                'prison': self.prisons[0].pk
            },
            {
                'prisoner_name': random_prisoner_name(),
                'prisoner_number': repeated_p_num_1,
                'prisoner_dob': random_prisoner_dob(),
                'prison': self.prisons[1].pk
            },
            {
                'prisoner_name': random_prisoner_name(),
                'prisoner_number': repeated_p_num_2,
                'prisoner_dob': random_prisoner_dob(),
                'prison': self.prisons[1].pk
            },
        ]
        response = self.client.post(
            self.list_url, data=data, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # test that total prisoner location records is now 3
        latest_created = PrisonerLocation.objects.all()
        self.assertEqual(latest_created.count(), len(data))
        for item in data:
            self.assertEqual(latest_created.filter(**item).count(), 1)

    def _test_validation_error(self, data, assert_error_msg):
        response = self.client.post(
            self.list_url, data=data, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.users[0])
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
            'Should fail because: {msg}'.format(msg=assert_error_msg)
        )

    def test_create_error_invalid_format(self):
        self._test_validation_error(
            data={},
            assert_error_msg='Should fail because invalid format (dict instead of list)'
        )

    def test_create_error_empty_list(self):
        self._test_validation_error(
            data=[{}],
            assert_error_msg='Should fail because empty data'
        )

    def test_create_error_invalid_dob(self):
        self._test_validation_error(
            data=[
                {
                    'prisoner_name': random_prisoner_name(),
                    'prisoner_number': random_prisoner_number(),
                    'prisoner_dob': '01//02//2015',
                    'prison': self.prisons[0].pk
                }
            ],
            assert_error_msg='Should fail because invalid dob'
        )

    def test_create_error_invalid_prison(self):
        self._test_validation_error(
            data=[
                {
                    'prisoner_name': random_prisoner_name(),
                    'prisoner_number': random_prisoner_number(),
                    'prisoner_dob': random_prisoner_dob(),
                    'prison': 'invalid'
                }
            ],
            assert_error_msg='Should fail because invalid prison'
        )

    @mock.patch('prison.serializers.credit_prisons_need_updating')
    def test_create_sends_credit_prisons_need_updating_signal(
        self, mocked_credit_prisons_need_updating
    ):
        user = self.users[0]

        data = [
            {
                'prisoner_name': random_prisoner_name(),
                'prisoner_number': random_prisoner_number(),
                'prisoner_dob': random_prisoner_dob(),
                'prison': self.prisons[0].pk
            }
        ]
        response = self.client.post(
            self.list_url, data=data, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        mocked_credit_prisons_need_updating.send.assert_called_with(sender=PrisonerLocation)


class PrisonerValidityViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        (self.prison_clerks, self.prisoner_location_admins,
         self.bank_admins, self.refund_bank_admins,
         self.send_money_users) = make_test_users()
        generate_transactions(transaction_batch=10)
        self.prisoner_locations = PrisonerLocation.objects.all()

    @property
    def url(self):
        return reverse('prisoner_validity-list')

    def get_valid_data(self):
        # theoretically, a valid query for GET
        prisoner_location_index = random.randrange(self.prisoner_locations.count())
        prisoner_location = self.prisoner_locations[prisoner_location_index]
        return {
            'prisoner_number': prisoner_location.prisoner_number,
            'prisoner_dob': format_date(prisoner_location.prisoner_dob, 'Y-m-d'),
        }

    def get_invalid_prisoner_number(self, cannot_equal):
        while True:
            prisoner_number = random_prisoner_number()
            if prisoner_number != cannot_equal:
                return prisoner_number

    def get_invalid_string_prisoner_dob(self, cannot_equal):
        while True:
            prisoner_dob = random_prisoner_dob()
            prisoner_dob = format_date(prisoner_dob, 'Y-m-d')
            if prisoner_dob != cannot_equal:
                return prisoner_dob

    def test_fails_without_authentication(self):
        for method in [self.client.get, self.client.post]:
            response = method(
                self.url,
                data=self.get_valid_data(),
                format='json'
            )
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED,
                             'for no user')

    def test_fails_without_application_permissions(self):
        """
        Tests that if the user logs in via a different application,
        they won't be able to access the API.
        """
        users_data = [
            (self.prison_clerks[0],
             self.get_http_authorization_for_user(self.prison_clerks[0])),
            (self.bank_admins[0],
             self.get_http_authorization_for_user(self.bank_admins[0])),
            (self.refund_bank_admins[0],
             self.get_http_authorization_for_user(self.refund_bank_admins[0])),
            (self.prisoner_location_admins[0],
             self.get_http_authorization_for_user(self.prisoner_location_admins[0])),
            (self.send_money_users[0],
             self.get_http_authorization_for_user(self.send_money_users[0],
                                                  client_id=CASHBOOK_OAUTH_CLIENT_ID)),
        ]
        for method in [self.client.get, self.client.post]:
            for user, http_auth_header in users_data:
                response = method(
                    self.url,
                    data=self.get_valid_data(),
                    format='json',
                    HTTP_AUTHORIZATION=http_auth_header,
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                                 'for user %s' % user)

    def test_missing_query_fails(self):
        http_auth_header = self.get_http_authorization_for_user(self.send_money_users[0])
        response = self.client.get(
            self.url,
            format='json',
            HTTP_AUTHORIZATION=http_auth_header,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()['errors'], "'prisoner_number' and 'prisoner_dob' fields are required")

    def test_missing_prisoner_number_fails(self):
        valid_data = self.get_valid_data()
        del valid_data['prisoner_number']
        http_auth_header = self.get_http_authorization_for_user(self.send_money_users[0])
        response = self.client.get(
            self.url,
            data=valid_data,
            format='json',
            HTTP_AUTHORIZATION=http_auth_header,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()['errors'], "'prisoner_number' and 'prisoner_dob' fields are required")

    def test_missing_prisoner_dob_fails(self):
        valid_data = self.get_valid_data()
        del valid_data['prisoner_dob']
        http_auth_header = self.get_http_authorization_for_user(self.send_money_users[0])
        response = self.client.get(
            self.url,
            data=valid_data,
            format='json',
            HTTP_AUTHORIZATION=http_auth_header,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()['errors'], "'prisoner_number' and 'prisoner_dob' fields are required")

    def test_valid_prisoner_details_return_same_data(self):
        valid_data = self.get_valid_data()
        http_auth_header = self.get_http_authorization_for_user(self.send_money_users[0])
        response = self.client.get(
            self.url,
            data=valid_data,
            format='json',
            HTTP_AUTHORIZATION=http_auth_header,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['count'], 1)
        self.assertSequenceEqual(response_data['results'], [valid_data])

    def test_invalid_prisoner_details_return_nothing(self):
        invalid_data = []
        invalid_data_item = self.get_valid_data()
        invalid_data_item['prisoner_number'] = self.get_invalid_prisoner_number(
            invalid_data_item['prisoner_number']
        )
        invalid_data.append(invalid_data_item)
        invalid_data_item = self.get_valid_data()
        invalid_data_item['prisoner_dob'] = self.get_invalid_string_prisoner_dob(
            invalid_data_item['prisoner_dob']
        )
        invalid_data.append(invalid_data_item)
        for data in invalid_data:
            http_auth_header = self.get_http_authorization_for_user(self.send_money_users[0])
            response = self.client.get(
                self.url,
                data=data,
                format='json',
                HTTP_AUTHORIZATION=http_auth_header,
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            response_data = response.json()
            self.assertEqual(response_data['count'], 0)
            self.assertSequenceEqual(response_data['results'], [])
