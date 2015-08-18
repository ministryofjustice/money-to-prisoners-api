from model_mommy import mommy

from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, \
    make_test_oauth_applications

from mtp_auth.tests.utils import AuthTestCaseMixin

from prison.models import Prison, PrisonerLocation

from prison.tests.utils import random_prisoner_number, random_prisoner_dob


class PrisonerLocationViewTestCase(AuthTestCaseMixin, APITestCase):
    fixtures = ['test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super(PrisonerLocationViewTestCase, self).setUp()
        self.prison_clerks, self.users, self.bank_admins = make_test_users()
        self.prisons = Prison.objects.all()
        make_test_oauth_applications()

    @property
    def list_url(self):
        return reverse('prisonerlocation-list')

    def test_fails_without_permissions(self):
        unauthorised_user = self.prison_clerks[0]

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
                'prisoner_number': random_prisoner_number(),
                'prisoner_dob': random_prisoner_dob(),
                'prison': self.prisons[0].pk
            },
            {
                'prisoner_number': repeated_p_num_1,
                'prisoner_dob': random_prisoner_dob(),
                'prison': self.prisons[1].pk
            },
            {
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
                    'prisoner_number': random_prisoner_number(),
                    'prisoner_dob': random_prisoner_dob(),
                    'prison': 'invalid'
                }
            ],
            assert_error_msg='Should fail because invalid prison'
        )
