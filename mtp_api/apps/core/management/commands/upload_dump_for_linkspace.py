import argparse
import logging
import pathlib
import re
import textwrap

from django.conf import settings
from django.core.management import BaseCommand, CommandError
import jwt
import requests

logger = logging.getLogger('mtp')


class Command(BaseCommand):
    """
    Upload a file to Linkspace
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        parser.add_argument('upload', type=argparse.FileType('rb'), help='Path of file to upload')
        parser.add_argument('table-name', help='Linkspace table to update')

    def handle(self, *args, **options):
        private_key_path = pathlib.Path(settings.LINKSPACE_PRIVATE_KEY_PATH)
        if not private_key_path.is_file():
            raise CommandError('Linkspace private key not found')
        if not settings.LINKSPACE_ENDPOINT:
            raise CommandError('Linkspace endpoint not specified')

        upload = options['upload']
        table_name = options['table-name']
        payload = {'table': table_name}
        token = jwt.encode(payload, private_key_path.read_bytes(), algorithm='RS256')

        response = requests.put(
            f'{settings.LINKSPACE_ENDPOINT}',
            data=upload,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}',
            },
            timeout=60,
        )
        is_error = response.status_code != 200
        import_result = 'but import undetermined'
        try:
            response_data = response.json()
        except ValueError:
            # response is not json
            is_error = True
        else:
            # use json content to determine error status and fall back to using http status
            is_error = response_data.get('is_error', is_error)
            message = response_data.get('message') or ''
            matches = re.search(r'processing as import ID (?P<import_id>\d+)', message)
            if matches:
                import_result = matches.group('import_id')
                import_result = f'will be processed with ID {import_result}'
            elif message == 'No data received, skipping':
                import_result = 'is empty, ignored'
            else:
                logger.warning(f'Linkspace response not parsed: {message}')

        if is_error:
            logger.error(f'Could not upload data to Linkspace:\n{response.content}')
        else:
            self.stdout.write(f'Successful upload to Linkspace {import_result}')
