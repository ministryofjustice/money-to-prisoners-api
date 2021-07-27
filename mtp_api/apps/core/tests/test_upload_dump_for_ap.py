from unittest import mock

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.conf import settings


class TestUploadDumpForAp(TestCase):
    def test_invalid_arguments(self):
        with self.assertRaises(CommandError, msg='file_path missing'):
            call_command('upload_dump_for_ap')
        with self.assertRaises(CommandError, msg='object_name missing'):
            call_command('upload_dump_for_ap', 'path/to/file')

    @mock.patch('core.management.commands.upload_dump_for_ap.upload_file_to_analytical_platform')
    @override_settings(ANALYTICAL_PLATFORM_BUCKET='')
    @override_settings(AWS_IAM_ROLE_ARN='test')
    @override_settings(ANALYTICAL_PLATFORM_BUCKET_PATH='test')
    def test_validating_if_bucked_name_is_not_present(self, mock_upload_file_to_analytical_platform):
        call_command('upload_dump_for_ap', 'some_path', settings.ANALYTICAL_PLATFORM_BUCKET)

        mock_upload_file_to_analytical_platform.assert_not_called()

    @mock.patch('core.management.commands.upload_dump_for_ap.upload_file_to_analytical_platform')
    @override_settings(ANALYTICAL_PLATFORM_BUCKET='test')
    @override_settings(AWS_IAM_ROLE_ARN='')
    @override_settings(ANALYTICAL_PLATFORM_BUCKET_PATH='test')
    def test_validating_if_iam_arn_role_is_not_present(self, mock_upload_file_to_analytical_platform):
        call_command('upload_dump_for_ap', 'some_path', 'bucket_name')

        mock_upload_file_to_analytical_platform.assert_not_called()

    @mock.patch('core.management.commands.upload_dump_for_ap.upload_file_to_analytical_platform')
    @override_settings(ANALYTICAL_PLATFORM_BUCKET='test')
    @override_settings(AWS_IAM_ROLE_ARN='test')
    @override_settings(ANALYTICAL_PLATFORM_BUCKET_PATH='')
    def test_validating_if_bucket_path_is_not_present(self, mock_upload_file_to_analytical_platform):
        call_command('upload_dump_for_ap', 'some_path', 'bucket_name')

        mock_upload_file_to_analytical_platform.assert_not_called()
