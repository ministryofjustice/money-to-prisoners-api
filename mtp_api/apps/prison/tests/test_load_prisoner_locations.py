import datetime

from django.core.management import call_command
from django.test import TestCase
import responses

from prison.models import PrisonerLocation, Prison


class LoadPrisonerLocationsTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json']
    oauth_url = 'https://offenders.local/oauth'
    offenders_url = 'https://offenders.local/offenders'

    def fake_response(self, rsps, *additional_offenders):
        rsps.add(rsps.POST, self.oauth_url, json={
            'access_token': '482298c239e9f8845a328cdd9bed9d0694595d0c24c7a8dfd0f45322e65b6c3b',
            'created_at': 1498820400,
            'expires_at': 1498827600,
            'expires_in': 7200,
            'scope': ['public'],
            'token_type': 'bearer',
        })
        rsps.add(rsps.GET, self.offenders_url, json=(
            {
                'id': '4a39e889-7abb-817c-e050-16ac01107c5c',
                'noms_id': 'A1409AE',
                'establishment_code': 'IXB',
                'title': None,
                'given_name_1': 'JAMES',
                'given_name_2': None,
                'given_name_3': None,
                'surname': 'HALLS',
                'suffix': None,
                'date_of_birth': '1989-01-21',
                'gender': 'M',
                'nationality_code': None,
                'pnc_number': None,
                'cro_number': None,
                'ethnicity_code': None,
            },
        ) + additional_offenders)
        rsps.add(rsps.GET, self.offenders_url, content_type='application/json', body=b'[]')

    def test_loads_ok(self):
        self.assertEqual(PrisonerLocation.objects.count(), 0)
        with responses.RequestsMock() as rsps:
            self.fake_response(rsps)
            call_command(
                'load_prisoner_locations',
                offender_endpoint=self.offenders_url,
                oauth_endpoint=self.oauth_url, oauth_client='abc', oauth_secret='123',
                page_size=1, verbosity=0,
            )
        self.assertEqual(PrisonerLocation.objects.count(), 1)
        location = PrisonerLocation.objects.first()
        self.assertEqual(str(location.single_offender_id), '4a39e889-7abb-817c-e050-16ac01107c5c')
        self.assertEqual(location.prison_id, 'IXB')
        self.assertEqual(location.prisoner_name, 'JAMES HALLS')
        self.assertEqual(location.prisoner_number, 'A1409AE')
        self.assertEqual(location.prisoner_dob, datetime.date(1989, 1, 21))
        self.assertIsNone(location.created_by)
        self.assertTrue(location.active)

    def test_ignores_unknown_prisons(self):
        self.assertEqual(PrisonerLocation.objects.count(), 0)
        Prison.objects.filter(nomis_id='IXB').delete()
        with responses.RequestsMock() as rsps:
            self.fake_response(rsps)
            call_command(
                'load_prisoner_locations',
                offender_endpoint=self.offenders_url,
                oauth_endpoint=self.oauth_url, oauth_client='abc', oauth_secret='123',
                page_size=1, verbosity=0,
            )
        self.assertEqual(PrisonerLocation.objects.count(), 0)

    def test_ignores_invalid_offenders(self):
        self.assertEqual(PrisonerLocation.objects.count(), 0)
        with responses.RequestsMock() as rsps:
            self.fake_response(rsps,
                               {
                                   'id': '300d5efe-bddc-4e17-8afd-1fd765ba3981',
                                   'noms_id': None,
                                   'establishment_code': 'INP',
                                   'given_name_1': 'JILLY',
                                   'surname': 'HALL',
                                   'date_of_birth': '1970-01-01',
                               },
                               {
                                   'id': '5506a0b6-9b86-49be-b4f3-db1a215f48c8',
                                   'noms_id': 'A1401AE',
                                   'establishment_code': 'INP',
                                   'given_name_1': 'JILLY',
                                   'surname': 'HALL',
                                   'date_of_birth': None,
                               },
                               )
            call_command(
                'load_prisoner_locations',
                offender_endpoint=self.offenders_url,
                oauth_endpoint=self.oauth_url, oauth_client='abc', oauth_secret='123',
                page_size=1, verbosity=0,
            )
        self.assertEqual(PrisonerLocation.objects.count(), 1)
        location = PrisonerLocation.objects.first()
        self.assertEqual(str(location.single_offender_id), '4a39e889-7abb-817c-e050-16ac01107c5c')
