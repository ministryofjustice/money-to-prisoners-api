from model_mommy import mommy

from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.utils import make_test_users, \
    make_test_oauth_applications

from prison.models import Prison, PrisonerLocation

from prison.tests.utils import random_prisoner_number, random_prisoner_dob


class PrisonerLocationViewTestCase(APITestCase):
    fixtures = ['test_prisons.json']

    def setUp(self):
        super(PrisonerLocationViewTestCase, self).setUp()
        self.users = make_test_users()
        self.prisons = Prison.objects.all()
        make_test_oauth_applications()

    @property
    def list_url(self):
        return reverse('prisonerlocation-list')

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

        self.client.force_authenticate(user=user)

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
            self.list_url, data=data, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # test that total prisoner location records is now 3
        latest_created = PrisonerLocation.objects.all()
        self.assertEqual(latest_created.count(), len(data))
        for item in data:
            self.assertEqual(latest_created.filter(**item).count(), 1)

    def test_create_validation_error(self):
        user = self.users[0]

        invalid_data_list = [
            {
                'data': {},
                'msg': 'Should fail because invalid format (dict instead of list)'
            },
            {
                'data': [
                    {}
                ],
                'msg': 'Should fail because empty data'
            },
            {
                'data': [
                    {
                        'prisoner_number': '*'*1000,
                        'prisoner_dob': random_prisoner_dob(),
                        'prison': self.prisons[0].pk
                    }
                ],
                'msg': 'Should fail because empty data'
            },
            {
                'data': [
                    {
                        'prisoner_number': random_prisoner_number(),
                        'prisoner_dob': '01//02//2015',
                        'prison': self.prisons[0].pk
                    }
                ],
                'msg': 'Should fail because invalid data format'
            },
            {
                'data': [
                    {
                        'prisoner_number': random_prisoner_number(),
                        'prisoner_dob': random_prisoner_dob(),
                        'prison': 'invalid'
                    }
                ],
                'msg': 'Should fail because invalid prison'
            },
        ]

        self.client.force_authenticate(user=user)

        for data in invalid_data_list:
            response = self.client.post(
                self.list_url, data=data['data'], format='json'
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                'Should fail because: {msg}'.format(msg=data['msg'])
            )
