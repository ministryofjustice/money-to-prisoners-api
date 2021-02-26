import re
import json

from django.conf import settings
from django.core.management import call_command
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
        self.prison_id = 'BWI'  # HMP Berwyn is present in dev HMPPS Prison API
        self.n_prisoners_api = 10
        self.n_prisoners_desired = 5

        self.prisoners = {}
        for _ in range(self.n_prisoners_api):
            prisoner_id = random_prisoner_number()
            self.prisoners[prisoner_id] = self.random_prisoner()

    def random_prisoner(self):
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

    def get_offender_info_callback(self, request):
        prisoner_id = request.path_url.split('/')[-1]
        prisoner_info = self.prisoners[prisoner_id]

        return (200, {}, json.dumps(prisoner_info))

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
            rsps.add(
                responses.GET,
                f'{settings.HMPPS_PRISON_API_BASE_URL}api/v1/prison/{self.prison_id}/live_roll',
                json={
                    'noms_ids': list(self.prisoners.keys()),
                }
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

        expected_prisoner_ids = list(self.prisoners.keys())
        expected_prisoner_ids.sort()
        for prisoner_id in expected_prisoner_ids[:self.n_prisoners_desired]:
            prisoner_info = self.prisoners[prisoner_id]

            location = PrisonerLocation.objects.filter(
                prisoner_number=prisoner_id,
                prison_id=self.prison_id,
            )

            self.assertTrue(location.exists())

            location = location.first()
            self.assertEqual(location.prisoner_number, prisoner_id)
            expected_name = prisoner_info['given_name'] + ' ' + prisoner_info['surname']
            self.assertEqual(location.prisoner_name, expected_name)
            self.assertEqual(str(location.prisoner_dob), prisoner_info['date_of_birth'])
