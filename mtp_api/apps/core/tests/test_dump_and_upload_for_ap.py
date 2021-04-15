import datetime
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from core.management.commands.dump_for_ap import Command as DumpCommand, Serialiser
from core.management.commands.upload_dump_for_ap import Command as UploadCommand


@override_settings(ANALYTICAL_PLATFORM_BUCKET='my-bucket')
class TestDumpAndUploadForAp(TestCase):
    @mock.patch.object(UploadCommand, 'handle')
    @mock.patch.object(DumpCommand, 'handle')
    @mock.patch('core.management.commands.dump_and_upload_for_ap.timezone')
    def test_dump_for_ap_command_calls_appropriate_commands(
        self,
        mocked_timezone,
        mocked_dump_for_ap,
        mocked_upload_dump_for_ap,
    ):
        mocked_timezone.localtime.return_value = datetime.datetime(
            2021, 3, 1, 13, 15,
            tzinfo=timezone.get_default_timezone()
        )
        mocked_dump_for_ap.return_value = None
        mocked_upload_dump_for_ap.return_value = None

        call_command('dump_and_upload_for_ap')

        expected_record_types = set(Serialiser.serialisers)

        record_types = set()
        for call in mocked_dump_for_ap.call_args_list:
            handle_kwargs = call[1]
            # ensure correct date range used
            self.assertEqual(handle_kwargs['after'], '2021-02-28')
            self.assertEqual(handle_kwargs['before'], '2021-03-01')
            record_types.add(handle_kwargs['type'])
        # ensure all record types are exported
        self.assertSetEqual(record_types, expected_record_types)

        record_types = set()
        for call in mocked_upload_dump_for_ap.call_args_list:
            handle_kwargs = call[1]
            object_name = handle_kwargs['object_name']
            # ensure S3 objects are named correctly
            self.assertTrue(object_name.startswith('2021-03-01_'))
            record_types.add(object_name[11:])
        # ensure all S3 objects are named correctly and all record types are covered
        self.assertSetEqual(record_types, expected_record_types)
