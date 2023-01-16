from collections import defaultdict
from copy import copy
import json
import re

from django.conf import settings
from django.test import override_settings, TestCase
import responses

from prison.models import PrisonerLocation
from prison.tests.utils import (
    load_prisoner_locations_from_dev_prison_api,
    random_prisoner_number,
    random_prisoner_name,
    random_prisoner_dob,
)


class LoadPrisonerLocationsFromDevPrisonAPITestCase(TestCase):
    fixtures = [
        'initial_types.json',
        'initial_groups.json',
        'dev_prison_api_prisons.json',
    ]

    def setUp(self):
        self.prison_ids = [
            'BWI',  # HMP Berwyn
            'NMI',  # HMP Nottingham
            'WLI',  # HMP Wayland
        ]
        prisoners_per_prison = {
            'BWI': 1,
            'NMI': 5,
            'WLI': 2,
        }
        # Dictionaries with data returned by mocked API
        self.api_live_roll = defaultdict(list)
        self.api_offenders_info = {}
        # Location of each test prisoner
        self.prisoner_location = {}

        for prison_id, n_prisoners in prisoners_per_prison.items():
            for _ in range(n_prisoners):
                prisoner_id = random_prisoner_number()
                prisoner_info = self.random_prisoner()

                self.api_live_roll[prison_id].append(prisoner_id)
                self.api_offenders_info[prisoner_id] = prisoner_info
                self.prisoner_location[prisoner_id] = prison_id

        self.n_prisoners_desired = 5
        # 1 prisoner from BWI
        self.expected_prisoner_ids = self.api_live_roll['BWI']
        # first 2 prisoners from NMI
        prisoners = copy(self.api_live_roll['NMI'])
        prisoners.sort()
        self.expected_prisoner_ids = self.expected_prisoner_ids + prisoners[:2]
        # another 2 prisoners from WLI
        self.expected_prisoner_ids = self.expected_prisoner_ids + self.api_live_roll['WLI']

    @classmethod
    def random_prisoner(cls):
        full_name = random_prisoner_name()
        first_name = full_name.split(' ')[0]
        last_name = full_name.split(' ')[1]
        return {
            'given_name': first_name,
            'middle_names': '',
            'surname': last_name,
            'date_of_birth': str(random_prisoner_dob()),
            # HMPPS Prison API returns more information not included here
        }

    def get_live_roll_callback(self, request):
        # Mock for `GET prison/PRISON_ID/live_roll`
        prison_id = request.path_url.split('/')[-2]
        live_roll = {
            'noms_ids': self.api_live_roll[prison_id],
        }

        return 200, {}, json.dumps(live_roll)

    def get_offender_info_callback(self, request):
        # Mock for `GET offenders/PRISONER_ID`
        prisoner_id = request.path_url.split('/')[-1]
        prisoner_info = self.api_offenders_info[prisoner_id]

        return 200, {}, json.dumps(prisoner_info)

    @override_settings(
        HMPPS_CLIENT_SECRET='test-secret',
        HMPPS_AUTH_BASE_URL='https://sign-in-dev.hmpps.local/auth/',
        HMPPS_PRISON_API_BASE_URL='https://api-dev.prison.local/',
    )
    def test_load_prisoner_locations_from_dev_prison_api(self):
        n_prisoner_locations_before = PrisonerLocation.objects.count()

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                f'{settings.HMPPS_AUTH_BASE_URL}oauth/token',
                json={
                    'access_token': 'amanaccesstoken',
                    'expires_in': 3600,
                },
            )
            rsps.add_callback(
                responses.GET,
                re.compile(f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/prison/[A-Z]+/live_roll'),
                callback=self.get_live_roll_callback,
            )
            rsps.add_callback(
                responses.GET,
                re.compile(f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/offenders/*'),
                callback=self.get_offender_info_callback,
            )

            load_prisoner_locations_from_dev_prison_api(self.n_prisoners_desired)

            n_prisoner_locations_after = PrisonerLocation.objects.count()
            n_prisoner_locations_created = n_prisoner_locations_after - n_prisoner_locations_before

            self.assertEqual(self.n_prisoners_desired, n_prisoner_locations_created)

            for prisoner_id in self.expected_prisoner_ids:
                prisoner_info = self.api_offenders_info[prisoner_id]
                prison_id = self.prisoner_location[prisoner_id]

                location = PrisonerLocation.objects.filter(
                    prisoner_number=prisoner_id,
                    prison_id=prison_id,
                )

                self.assertTrue(location.exists())

                location = location.first()
                self.assertEqual(location.prisoner_number, prisoner_id)
                expected_name = prisoner_info['given_name'] + ' ' + prisoner_info['surname']
                self.assertEqual(location.prisoner_name, expected_name)
                self.assertEqual(str(location.prisoner_dob), prisoner_info['date_of_birth'])
