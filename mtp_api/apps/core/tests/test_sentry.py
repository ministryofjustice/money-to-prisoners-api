from django.test import SimpleTestCase

from core.sentry import scrub_prisoner_details


def make_event(path, query_string):
    frames = [
        {'function': 'list', 'vars': {'prisoner_number': "'A1409AE'", 'prisoner_dob': "'1989-01-21'"}},
    ]
    return {
        'request': {
            'url': f'http://api.local{path}',
            'method': 'GET',
            'query_string': query_string,
        },
        'exception': {'values': [{'type': 'ValueError', 'stacktrace': {'frames': frames}}]},
        'threads': {'values': [{'id': 1, 'stacktrace': {'frames': [dict(frame) for frame in frames]}}]},
    }


class ScrubPrisonerDetailsTestCase(SimpleTestCase):
    def test_prisoner_details_removed_from_prisoner_validity_errors(self):
        event = make_event('/prisoner_validity/', 'prisoner_number=A1409AE&prisoner_dob=1989-01-21')
        event = scrub_prisoner_details(event, {})

        self.assertNotIn('query_string', event['request'])
        self.assertEqual(event['request']['url'], 'http://api.local/prisoner_validity/')
        for key in ('exception', 'threads'):
            frame = event[key]['values'][0]['stacktrace']['frames'][0]
            self.assertNotIn('vars', frame)
            self.assertEqual(frame['function'], 'list')
        self.assertNotIn('A1409AE', str(event))
        self.assertNotIn('1989-01-21', str(event))

    def test_prisoner_details_removed_when_only_transaction_set(self):
        event = make_event('/prisoner_validity/', 'prisoner_number=A1409AE&prisoner_dob=1989-01-21')
        event['request'] = {'data': ''}
        event['transaction'] = '/prisoner_validity/'
        event = scrub_prisoner_details(event, {})

        self.assertNotIn('A1409AE', str(event))
        self.assertNotIn('1989-01-21', str(event))

    def test_other_errors_unchanged(self):
        event = make_event('/credits/', 'prisoner_number=A1409AE')
        self.assertEqual(scrub_prisoner_details(event, {}), make_event('/credits/', 'prisoner_number=A1409AE'))

    def test_events_without_requests_unchanged(self):
        event = {'message': 'Something went wrong', 'exception': {'values': [{'type': 'ValueError'}]}}
        self.assertEqual(scrub_prisoner_details(event, {}), {
            'message': 'Something went wrong', 'exception': {'values': [{'type': 'ValueError'}]},
        })
