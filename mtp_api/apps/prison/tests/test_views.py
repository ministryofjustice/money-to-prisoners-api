import itertools
import random
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils.dateformat import format as format_date
from model_mommy import mommy
from mtp_common.nomis import Connector
from mtp_common.test_utils import silence_logger
from parameterized import parameterized
import requests
import responses
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users
from mtp_auth.tests.utils import AuthTestCaseMixin
from mtp_auth.constants import CASHBOOK_OAUTH_CLIENT_ID
from mtp_auth.models import PrisonUserMapping
from prison.models import Prison, PrisonerLocation, Population, Category
from prison.tests.utils import (
    random_prisoner_name, random_prisoner_number, random_prisoner_dob,
    load_random_prisoner_locations
)


class PrisonerLocationViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=2)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.send_money_users = test_users['send_money_users']
        self.prisons = Prison.objects.all()

    @property
    def list_url(self):
        return reverse('prisonerlocation-list')

    def retrieve_url(self, prisoner_number):
        return reverse('prisonerlocation-detail', kwargs={'prisoner_number': prisoner_number})

    @property
    def delete_old_url(self):
        return reverse('prisonerlocation-delete-old')

    @property
    def delete_inactive_url(self):
        return reverse('prisonerlocation-delete-inactive')

    def test_fails_without_application_permissions(self):
        """
        Tests that if the user logs in via a different application,
        they won't be able to access the API.
        """
        users_data = [
            (
                self.bank_admins[0],
                self.get_http_authorization_for_user(self.bank_admins[0])
            ),
            (
                self.refund_bank_admins[0],
                self.get_http_authorization_for_user(self.refund_bank_admins[0])
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
        unauthorised_user = self.prisoner_location_admins[0]

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
        user = self.prisoner_location_admins[0]

        repeated_p_num_1 = random_prisoner_number()
        repeated_p_num_2 = random_prisoner_number()
        # create two pre-existing PrisonerLocations so that we test the overwrite
        mommy.make(PrisonerLocation, prisoner_number=repeated_p_num_1,
                   prison=self.prisons[0], active=True)
        mommy.make(PrisonerLocation, prisoner_number=repeated_p_num_2,
                   prison=self.prisons[0], active=True)
        self.assertEqual(PrisonerLocation.objects.filter(active=True).count(), 2)
        self.assertEqual(PrisonerLocation.objects.filter(active=False).count(), 0)

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

        self.assertEqual(PrisonerLocation.objects.filter(active=True).count(), 2)
        # test that inactive prisoner location records is now 3
        latest_created = PrisonerLocation.objects.filter(active=False)
        self.assertEqual(latest_created.count(), 3)
        for item in data:
            self.assertEqual(latest_created.filter(**item).count(), 1)

        return data

    def test_create_and_delete_old(self):
        data = self.test_create()
        self.client.post(
            self.delete_old_url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.prisoner_location_admins[0])
        )
        self.assertEqual(PrisonerLocation.objects.filter(active=True).count(), 3)
        self.assertEqual(PrisonerLocation.objects.filter(active=False).count(), 0)
        for item in data:
            self.assertEqual(
                PrisonerLocation.objects.filter(active=True).filter(**item).count(),
                1
            )

    def test_create_and_delete_inactive(self):
        data = self.test_create()
        self.client.post(
            self.delete_inactive_url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.prisoner_location_admins[0])
        )
        self.assertEqual(PrisonerLocation.objects.filter(active=True).count(), 2)
        self.assertEqual(PrisonerLocation.objects.filter(active=False).count(), 0)
        for item in data:
            self.assertEqual(
                PrisonerLocation.objects.filter(active=True).filter(**item).count(),
                0
            )

    def _test_validation_error(self, data, assert_error_msg):
        response = self.client.post(
            self.list_url, data=data, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.prisoner_location_admins[0])
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

    def test_retrieve(self):
        load_random_prisoner_locations()
        user = self.prison_clerks[0]

        prisoner = PrisonerLocation.objects.filter(
            prison__in=PrisonUserMapping.objects.get_prison_set_for_user(user)
        ).first()

        response = self.client.get(
            self.retrieve_url(prisoner.prisoner_number), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_fails_for_prisoner_not_in_own_prison(self):
        load_random_prisoner_locations()
        user = self.prison_clerks[0]

        prisoner = PrisonerLocation.objects.exclude(
            prison__in=PrisonUserMapping.objects.get_prison_set_for_user(user)
        ).first()

        response = self.client.get(
            self.retrieve_url(prisoner.prisoner_number), format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DeleteOldPrisonerLocationsViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=2)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.send_money_users = test_users['send_money_users']
        load_random_prisoner_locations(50)
        self.assertEqual(PrisonerLocation.objects.filter(active=True).count(), 50)

    @property
    def url(self):
        return reverse('prisonerlocation-delete-old')

    def test_cannot_delete_if_not_logged_in(self):
        response = self.client.post(
            self.url, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_fails_without_action_permissions(self):
        response = self.client.post(
            self.url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.prison_clerks[0])
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

    def test_delete_old(self):
        response = self.client.post(
            self.url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.prisoner_location_admins[0])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.assertEqual(PrisonerLocation.objects.all().count(), 0)

    @mock.patch('prison.views.prisoner_profile_current_prisons_need_updating')
    @mock.patch('prison.views.credit_prisons_need_updating')
    def test_delete_old_sends_prisons_need_updating_signals(
        self, mocked_credit_prisons_need_updating, mocked_prisoner_profiles_need_updating
    ):
        response = self.client.post(
            self.url, format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.prisoner_location_admins[0])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        mocked_credit_prisons_need_updating.send.assert_called_with(sender=PrisonerLocation)
        mocked_prisoner_profiles_need_updating.send.assert_called_with(sender=PrisonerLocation)


class PrisonerValidityViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=2)
        self.prison_clerks = test_users['prison_clerks']
        self.prisoner_location_admins = test_users['prisoner_location_admins']
        self.bank_admins = test_users['bank_admins']
        self.refund_bank_admins = test_users['refund_bank_admins']
        self.send_money_users = test_users['send_money_users']
        load_random_prisoner_locations()
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

    def assertValidResponse(self, response, expected_data):  # noqa: N802
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['count'], 1)
        self.assertSequenceEqual(response_data['results'], [expected_data])

    def assertEmptyResponse(self, response):  # noqa: N802
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['count'], 0)
        self.assertSequenceEqual(response_data['results'], [])

    def call_authorised_endpoint(self, get_params):
        http_auth_header = self.get_http_authorization_for_user(self.send_money_users[0])
        return self.client.get(
            self.url,
            data=get_params,
            format='json',
            HTTP_AUTHORIZATION=http_auth_header,
        )

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
        response = self.call_authorised_endpoint(valid_data)
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
        response = self.call_authorised_endpoint(valid_data)
        self.assertValidResponse(response, valid_data)

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
            response = self.call_authorised_endpoint(data)
            self.assertEmptyResponse(response)

    def test_valid_prisoner_found_with_correct_prison_filter(self):
        valid_data = self.get_valid_data()
        prisoner_location = PrisonerLocation.objects.get(prisoner_number=valid_data['prisoner_number'])
        valid_data_with_filter = valid_data.copy()
        valid_data_with_filter['prisons'] = prisoner_location.prison.nomis_id
        response = self.call_authorised_endpoint(valid_data_with_filter)
        self.assertValidResponse(response, valid_data)

    def test_valid_prisoner_found_with_multiple_correct_prison_filter(self):
        valid_data = self.get_valid_data()
        valid_data_with_filter = valid_data.copy()
        valid_data_with_filter['prisons'] = ','.join(Prison.objects.values_list('nomis_id', flat=True))
        response = self.call_authorised_endpoint(valid_data_with_filter)
        self.assertValidResponse(response, valid_data)

    def test_valid_prisoner_not_found_with_incorrect_prison_filter(self):
        valid_data = self.get_valid_data()
        prisoner_location = PrisonerLocation.objects.get(prisoner_number=valid_data['prisoner_number'])
        other_prisons = Prison.objects.exclude(nomis_id=prisoner_location.prison.nomis_id)
        if other_prisons.count() == 0:
            self.fail('Cannot test prisoner validity filtering as there are insufficient prisons')
        valid_data_with_filter = valid_data.copy()
        valid_data_with_filter['prisons'] = ','.join(other_prisons.values_list('nomis_id', flat=True))
        response = self.call_authorised_endpoint(valid_data_with_filter)
        self.assertEmptyResponse(response)


class PrisonerAccountBalanceTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()

        # make 1 prisoner in a public prison and in a private one
        public_prison = Prison.objects.get(nomis_id='INP')
        public_prison.private_estate = False
        public_prison.save()
        private_prison = Prison.objects.get(nomis_id='IXB')
        private_prison.private_estate = True
        private_prison.save()
        load_random_prisoner_locations(number_of_prisoners=2)
        prisoner_locations = PrisonerLocation.objects.order_by('?')[0:2]
        prisoner_location_public, prisoner_location_private = prisoner_locations
        prisoner_location_public.prison = public_prison
        prisoner_location_public.save()
        prisoner_location_private.prison = private_prison
        prisoner_location_private.save()
        self.prisoner_location_public = prisoner_location_public
        self.prisoner_location_private = prisoner_location_private

        # make standard users
        test_users = make_test_users(clerks_per_prison=1, num_security_fiu_users=0)
        send_money_users = test_users.pop('send_money_users')
        self.send_money_user = send_money_users[0]
        self.other_users = itertools.chain.from_iterable(test_users.values())

    @staticmethod
    def tearDown():
        cache.clear()

    def make_api_call(self, prisoner_location, user=None):
        prisoner_number = prisoner_location.prisoner_number
        url = reverse('prisoner_account_balance-detail', kwargs={'prisoner_number': prisoner_number})
        kwargs = {'format': 'json'}
        if user:
            kwargs['HTTP_AUTHORIZATION'] = self.get_http_authorization_for_user(user)
        return self.client.get(url, **kwargs)

    def test_fails_without_authentication(self):
        response = self.make_api_call(self.prisoner_location_public)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, msg='access without auth')

    def test_fails_without_application_permissions(self):
        for another_user in self.other_users:
            response = self.make_api_call(self.prisoner_location_public, another_user)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, msg=f'accessed by {another_user}')

    @mock.patch('prison.serializers.nomis')
    def test_retrieving_combined_balance_in_public_estate(self, mocked_nomis):
        mocked_nomis.get_account_balances.return_value = {'cash': 3000, 'spends': 550, 'savings': 12000}

        response = self.make_api_call(self.prisoner_location_public, self.send_money_user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertDictEqual(response_data, {'combined_account_balance': 3000 + 550 + 12000})

    @mock.patch('prison.serializers.nomis')
    def test_retrieving_combined_balance_in_private_estate(self, mocked_nomis):
        mocked_nomis.get_account_balances.return_value = {'cash': 1000, 'spends': 550, 'savings': 12000}

        response = self.make_api_call(self.prisoner_location_private, self.send_money_user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertDictEqual(response_data, {'combined_account_balance': 0})
        mocked_nomis.get_account_balances.assert_not_called()

    @mock.patch('prison.serializers.nomis')
    def test_nomis_error_propagates(self, mocked_nomis):
        mocked_nomis.get_account_balances.side_effect = requests.HTTPError('403 Client Error: FORBIDDEN')

        with silence_logger():
            response = self.make_api_call(self.prisoner_location_public, self.send_money_user)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'Cannot lookup NOMIS balances', response.content)

    @mock.patch('prison.serializers.nomis')
    def test_nomis_response_with_missing_accounts(self, mocked_nomis):
        mocked_nomis.get_account_balances.return_value = {'cash': 0}

        with silence_logger():
            response = self.make_api_call(self.prisoner_location_public, self.send_money_user)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'malformed', response.content)

    @mock.patch('prison.serializers.nomis')
    def test_nomis_response_with_unexpected_account_values(self, mocked_nomis):
        mocked_nomis.get_account_balances.return_value = {'cash': 1000, 'spends': 550, 'savings': None}

        with silence_logger():
            response = self.make_api_call(self.prisoner_location_public, self.send_money_user)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'malformed', response.content)

    @override_settings(
        HMPPS_CLIENT_SECRET='EXAMPLE',
        HMPPS_AUTH_BASE_URL='https://sign-in-dev.hmpps.local/auth/',
        HMPPS_PRISON_API_BASE_URL='https://api-dev.prison.local/',
    )
    @mock.patch('mtp_api.apps.prison.serializers.nomis.connector', Connector())
    def test_prisoner_location_mismatch_prisoner_found(self, *args):
        # We need more than one public prison!
        Prison.objects.update(private_estate=False)
        existing_prison = self.prisoner_location_public.prison
        new_prison = Prison.objects.filter(
            private_estate=False
        ).exclude(
            nomis_id=self.prisoner_location_public.prison.nomis_id,
        ).first()

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                f'{settings.HMPPS_AUTH_BASE_URL}oauth/token',
                json={
                    'access_token': 'amanaccesstoken',
                    'expires_in': 3600
                }
            )
            rsps.add(
                responses.GET,
                f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/prison/{self.prisoner_location_public.prison.nomis_id}/offenders/{self.prisoner_location_public.prisoner_number}/accounts',  # noqa: E501
                status=400,
                json={'thisshouldnot': 'matter'}
            )
            rsps.add(
                responses.GET,
                f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/offenders/{self.prisoner_location_public.prisoner_number}/location',  # noqa: E501
                json={
                    'establishment': {
                        'code': new_prison.nomis_id,
                        'desc': new_prison.name
                    },
                }
            )
            rsps.add(
                responses.GET,
                f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/prison/{new_prison.nomis_id}/offenders/{self.prisoner_location_public.prisoner_number}/accounts',  # noqa: E501
                status=200,
                json={
                    'cash': 1000, 'spends': 550, 'savings': 12000
                }
            )
            response = self.make_api_call(self.prisoner_location_public, self.send_money_user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('combined_account_balance', response.json().keys())

        self.prisoner_location_public.refresh_from_db()
        self.assertEqual(self.prisoner_location_public.prison, existing_prison)

    @override_settings(
        HMPPS_CLIENT_SECRET='EXAMPLE',
        HMPPS_AUTH_BASE_URL='https://sign-in-dev.hmpps.local/auth/',
        HMPPS_PRISON_API_BASE_URL='https://api-dev.prison.local/',
    )
    @mock.patch('mtp_api.apps.prison.serializers.nomis.connector', Connector())
    def test_prisoner_location_mismatch_no_prisoner_found(self, *args):
        initial_prison = self.prisoner_location_public.prison

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                f'{settings.HMPPS_AUTH_BASE_URL}oauth/token',
                json={
                    'access_token': 'amanaccesstoken',
                    'expires_in': 3600
                }
            )
            rsps.add(
                responses.GET,
                f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/prison/{self.prisoner_location_public.prison.nomis_id}/offenders/{self.prisoner_location_public.prisoner_number}/accounts',  # noqa: E501
                status=400,
                json={'thisshouldnot': 'matter'}
            )
            rsps.add(
                responses.GET,
                f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/offenders/{self.prisoner_location_public.prisoner_number}/location',  # noqa: E501
                status=400,
            )
            response = self.make_api_call(self.prisoner_location_public, self.send_money_user)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            f'Could not find location for prisoner_number {self.prisoner_location_public.prisoner_number} in NOMIS',
            response.json()
        )

        self.prisoner_location_public.refresh_from_db()
        self.assertEqual(self.prisoner_location_public.prison, initial_prison)


    @parameterized.expand([
        (status.HTTP_404_NOT_FOUND,),
        (status.HTTP_500_INTERNAL_SERVER_ERROR,),
        (status.HTTP_502_BAD_GATEWAY,),
        (status.HTTP_503_SERVICE_UNAVAILABLE,),
        (status.HTTP_504_GATEWAY_TIMEOUT,),
        (status.HTTP_507_INSUFFICIENT_STORAGE,),
    ])
    @mock.patch('mtp_api.apps.prison.serializers.nomis.connector', Connector())
    @override_settings(
        HMPPS_CLIENT_SECRET='EXAMPLE',
        HMPPS_AUTH_BASE_URL='https://sign-in-dev.hmpps.local/auth/',
        HMPPS_PRISON_API_BASE_URL='https://api-dev.prison.local/',
    )
    def test_nomis_outage(self, status_code, *args):
        expected_response = {
            'combined_account_balance': 0
        }
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                f'{settings.HMPPS_AUTH_BASE_URL}oauth/token',
                json={
                    'access_token': 'amanaccesstoken',
                    'expires_in': 3600
                }
            )
            rsps.add(
                responses.GET,
                f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/prison/{self.prisoner_location_public.prison.nomis_id}/offenders/{self.prisoner_location_public.prisoner_number}/accounts',  # noqa: E501
                status=status_code,
            )
            response = self.make_api_call(self.prisoner_location_public, self.send_money_user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), expected_response)

class PrisonViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users(clerks_per_prison=2)
        prison_clerks = test_users['prison_clerks']
        bank_admins = test_users['bank_admins']
        send_money_users = test_users['send_money_users']
        security_staff = test_users['security_staff']
        self.users = prison_clerks[0], bank_admins[0], send_money_users[0], security_staff[0]
        self.send_money_user = send_money_users[0]
        load_random_prisoner_locations(number_of_prisoners=2 * Prison.objects.count())

    def test_list_prisons(self):
        url = reverse('prison-list')
        prison_set = set(Prison.objects.values_list('name', flat=True))
        self.assertTrue(prison_set)
        for user in self.users:
            response = self.client.get(url, HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
                                       format='json')
            self.assertSetEqual(set(prison['name'] for prison in response.data['results']), prison_set)

    def test_exclude_empty_prisons(self):
        url = reverse('prison-list')
        empty_prison = mommy.make(Prison, name='Empty')
        response = self.client.get(url + '?exclude_empty_prisons=True',
                                   HTTP_AUTHORIZATION=self.get_http_authorization_for_user(self.send_money_user),
                                   format='json')
        self.assertEqual(response.data['count'], Prison.objects.count() - 1)
        self.assertNotIn(bytes(empty_prison.nomis_id, encoding='utf-8'), response.content)


class PrisonPopulationViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks = make_test_users()['prison_clerks']

    @property
    def url(self):
        return reverse('prison_population-list')

    def test_list_prison_categories(self):
        user = self.prison_clerks[0]
        response = self.client.get(
            self.url,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )

        self.assertEqual(len(Population.objects.all()), response.data['count'])
        for prison_category in response.data['results']:
            self.assertTrue(prison_category['name'] in Population.objects.all().values_list('name', flat=True))


class PrisonCategoryViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.prison_clerks = make_test_users()['prison_clerks']

    @property
    def url(self):
        return reverse('prison_category-list')

    def test_list_prison_categories(self):
        user = self.prison_clerks[0]
        response = self.client.get(
            self.url,
            format='json',
            HTTP_AUTHORIZATION=self.get_http_authorization_for_user(user),
        )

        self.assertEqual(len(Category.objects.all()), response.data['count'])
        for prison_category in response.data['results']:
            self.assertTrue(prison_category['name'] in Category.objects.all().values_list('name', flat=True))
