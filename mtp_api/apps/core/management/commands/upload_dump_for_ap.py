import textwrap

import boto3
from django.conf import settings
from django.core.management import BaseCommand


class Command(BaseCommand):
    """
    Upload a file to an S3 bucket in Analytical Platform
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        parser.add_argument('file_path', help='Path of file to upload')
        parser.add_argument('object_name', help='Name of the object being stored in S3')

    def handle(self, *args, **options):
        if not all([settings.ANALYTICAL_PLATFORM_BUCKET,
                    settings.ANALYTICAL_PLATFORM_BUCKET_PATH]):
            self.stderr.write(self.style.WARNING('Cannot upload dump to Analytical Platform'))
            return

        upload_file_to_analytical_platform(options['file_path'], options['object_name'])


def upload_file_to_analytical_platform(file_path, target_name):
    if settings.ANALYTICAL_PLATFORM_BUCKET_PATH:
        target_name = f'{settings.ANALYTICAL_PLATFORM_BUCKET_PATH}/{target_name}'
    s3_client = boto3.client('s3')
    s3_client.upload_file(
        Filename=file_path, Bucket=settings.ANALYTICAL_PLATFORM_BUCKET, Key=target_name,
        ExtraArgs={'ACL': 'bucket-owner-full-control', 'ServerSideEncryption': 'AES256'},
    )
