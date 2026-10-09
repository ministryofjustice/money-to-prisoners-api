from django.test import SimpleTestCase

from core.sentry import scrub_prisoner_details


def make_event(path, query_string):
    # local variables are not sent (`include_local_variables=False`) so frames have none
    frames = [{'function': 'list', 'module': 'prison.views'}]
    return {
        'request': {
            'url': f'http://api.local{path}',
            'method': 'GET',
            'query_string': query_string,
        },
        'exception': {'values': [{'type': 'ValueError', 'value': 'invalid', 'stacktrace': {'frames': frames}}]},
        'threads': {'values': [{'id': 1, 'stacktrace': {'frames': [dict(frame) for frame in frames]}}]},
    }


class ScrubPrisonerDetailsTestCase(SimpleTestCase):
    def test_query_string_removed_from_prisoner_validity_errors(self):
        event = make_event('/prisoner_validity/', 'prisoner_number=A1409AE&prisoner_dob=1989-01-21')
        event = scrub_prisoner_details(event, {})

        self.assertNotIn('query_string', event['request'])
        self.assertEqual(event['request']['url'], 'http://api.local/prisoner_validity/')
        self.assertEqual(event['exception']['values'][0]['stacktrace']['frames'][0]['function'], 'list')
        self.assertNotIn('A1409AE', str(event))
        self.assertNotIn('1989-01-21', str(event))

    def test_submitted_values_removed_from_messages(self):
        event = make_event('/prisoner_validity/', 'prisoner_number=A1409AE&prisoner_dob=1989-01-21')
        event['exception']['values'][0]['value'] = "invalid prisoner 'A1409AE' born 1989-01-21"
        event['logentry'] = {'message': 'Lookup failed for %s', 'params': ['A1409AE']}
        event['breadcrumbs'] = {'values': [{'category': 'mtp', 'message': 'Checking A1409AE'}]}
        event = scrub_prisoner_details(event, {})

        self.assertNotIn('A1409AE', str(event))
        self.assertNotIn('1989-01-21', str(event))
        self.assertEqual(event['exception']['values'][0]['value'], "invalid prisoner '[Filtered]' born [Filtered]")
        self.assertEqual(event['logentry'], {'message': 'Lookup failed for %s', 'params': ['[Filtered]']})
        self.assertEqual(event['breadcrumbs']['values'][0]['message'], 'Checking [Filtered]')

    def test_short_submitted_values_not_redacted(self):
        event = make_event('/prisoner_validity/', 'prisoner_number=A&prisoner_dob=1')
        event['exception']['values'][0]['value'] = 'A problem occurred'
        event = scrub_prisoner_details(event, {})

        self.assertEqual(event['exception']['values'][0]['value'], 'A problem occurred')

    def test_query_string_removed_when_only_transaction_set(self):
        event = make_event('/prisoner_validity/', 'prisoner_number=A1409AE&prisoner_dob=1989-01-21')
        event['request'] = {'data': '', 'query_string': 'prisoner_number=A1409AE&prisoner_dob=1989-01-21'}
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
