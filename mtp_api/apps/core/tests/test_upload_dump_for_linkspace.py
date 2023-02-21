import os
import pathlib
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.test.utils import captured_stdout
import jwt
import responses

TEST_PRIVATE_KEY = pathlib.Path(__file__).absolute().parent / 'test-key.pem'


class TestUploadDumpForLinkspace(TestCase):
    def setUp(self):
        super().setUp()
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.write(b'[{"Internal ID": 123333, "Created at": "2020-06-01 12:00:00"}]')
        self.temp_file.flush()

    def tearDown(self):
        super().tearDown()
        try:
            self.temp_file.close()
            os.unlink(self.temp_file.name)
        except:  # noqa: B001, E722
            pass

    @override_settings(
        LINKSPACE_ENDPOINT='',
        LINKSPACE_PRIVATE_KEY_PATH='',
    )
    def test_missing_settings(self):
        with self.assertRaises(CommandError), responses.RequestsMock():
            call_command('upload_dump_for_linkspace', self.temp_file.name, 'fiucredits')

    @override_settings(
        LINKSPACE_ENDPOINT='https://linkspace.local/upload/',
        LINKSPACE_PRIVATE_KEY_PATH=TEST_PRIVATE_KEY,
    )
    def test_successful_upload(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.PUT,
                'https://linkspace.local/upload/',
                json={'message': 'Data received successfully, processing as import ID 992', 'is_error': False},
            )
            with captured_stdout() as stdout:
                call_command('upload_dump_for_linkspace', self.temp_file.name, 'fiucredits')
            request = rsps.calls[0].request

        self.assertEqual(request.headers['Content-Type'], 'application/json')
        auth = request.headers['Authorization']
        self.assertTrue(auth.startswith('Bearer '))
        token = auth[len('Bearer '):]
        test_private_key = serialization.load_pem_private_key(
            TEST_PRIVATE_KEY.read_bytes(),
            password=None,
            backend=default_backend(),
        )
        test_public_key = test_private_key.public_key()
        payload = jwt.decode(token, test_public_key, algorithms=['RS256'])
        self.assertDictEqual(payload, {'table': 'fiucredits'})
        stdout = stdout.getvalue()
        self.assertIn('processed with ID 992', stdout)

    @override_settings(
        LINKSPACE_ENDPOINT='https://linkspace.local/upload/',
        LINKSPACE_PRIVATE_KEY_PATH=TEST_PRIVATE_KEY,
    )
    def test_failed_upload(self):
        with self.assertRaises(CommandError), responses.RequestsMock() as rsps:
            rsps.add(
                responses.PUT,
                'https://linkspace.local/upload/',
                json={'message': 'Table not found: fiumissing', 'is_error': True},
            )
            call_command('upload_dump_for_linkspace', self.temp_file.name, 'fiumissing')
