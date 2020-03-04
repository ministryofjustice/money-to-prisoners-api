from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings


class TestDumpAndUploadForAp(TestCase):
    @mock.patch('core.management.commands.dump_and_upload_for_ap.upload_dump_for_ap_command')
    @mock.patch('core.management.commands.dump_and_upload_for_ap.dump_for_ap_command')
    def test_dump_for_ap_command_is_called(self,
                                           mock_dump_for_ap_command,
                                           mock_upload_dump_for_ap_command):

        call_command('dump_and_upload_for_ap')

        assert mock_dump_for_ap_command.called

    @mock.patch('core.management.commands.dump_and_upload_for_ap.upload_dump_for_ap_command')
    @override_settings(ANALYTICAL_PLATFORM_BUCKET='my-bucket')
    def test_upload_dump_for_ap_command_is_called(self, mock_upload_for_ap_command):

        call_command('dump_and_upload_for_ap')

        assert mock_upload_for_ap_command.called
