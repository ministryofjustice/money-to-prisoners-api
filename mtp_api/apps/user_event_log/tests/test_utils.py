from datetime import datetime
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.timezone import make_aware
from model_bakery import baker

from user_event_log.constants import USER_EVENT_KINDS
from user_event_log.utils import record_user_event

User = get_user_model()


class RecordUserEventTestCase(TestCase):
    """
    Tests related to the record_user_event util function.
    """
    def test(self):
        """Test record_user_event."""
        scenarios = [
            (None, None),

            (
                {'a': 'b'},
                {'a': 'b'},
            ),

            (
                {'a': make_aware(datetime(2018, 4, 15, 12))},
                {'a': '2018-04-15T12:00:00+01:00'},
            ),

            ('string', 'string'),

            ([0, 2, 3], [0, 2, 3]),

            # if obj cannot be encoded by django but has a pk attr, use that
            (
                {'obj': [Mock(pk=123)]},
                {'obj': [123]},
            ),

            # if obj cannot be encoded by django and doesn't have any pk attr, use str(...)
            (
                object,
                "<class 'object'>",
            ),
        ]

        user = baker.make(User)

        request = Mock(user=user, path='test-path')
        for data, expected_data in scenarios:
            event = record_user_event(request, USER_EVENT_KINDS.NOMS_OPS_SEARCH, data=data)
            event.refresh_from_db()

            self.assertEqual(event.user, user)
            self.assertEqual(event.kind, USER_EVENT_KINDS.NOMS_OPS_SEARCH)
            self.assertEqual(event.api_url_path, 'test-path')
            self.assertEqual(event.data, expected_data)
