import textwrap
import os

import boto3
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    """
    Upload file to S3
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        parser.add_argument('file_path', help='Path to dump data')
        parser.add_argument('object_name', help='Name of the file being stored in AWS S3')

    def handle(self, *args, **options):
        if not all([settings.ANALYTICAL_PLATFORM_BUCKET,
                    settings.AWS_IAM_ROLE_ARN,
                    settings.ANALYTICAL_PLATFORM_BUCKET_PATH]):
            self.stderr.write(self.style.WARNING('Cannot upload dump to Analytical Platform'))
            return

        upload_file_to_analytical_platform(options['file_path'], options['object_name'])


def get_aws_credentials():
    if settings.AWS_IAM_ROLE_ARN:
        sts_client = boto3.client('sts')
        session_name = os.environ.get('POD_NAME') or settings.APP
        session_name = f'mtp-{session_name}'
        assumed_role = sts_client.assume_role(
            RoleArn=settings.AWS_IAM_ROLE_ARN, RoleSessionName=session_name,
        )
        credentials = assumed_role['Credentials']
        return {
            'aws_access_key_id': credentials['AccessKeyId'],
            'aws_secret_access_key': credentials['SecretAccessKey'],
            'aws_session_token': credentials['SessionToken'],
        }
    return {}


def upload_file_to_analytical_platform(file_path, target_name):
    if settings.ANALYTICAL_PLATFORM_BUCKET_PATH:
        target_name = f'{settings.ANALYTICAL_PLATFORM_BUCKET_PATH}/{target_name}'
    s3_client = boto3.client('s3', **get_aws_credentials())
    s3_client.upload_file(
        Filename=file_path, Bucket=settings.ANALYTICAL_PLATFORM_BUCKET, Key=target_name,
        ExtraArgs={'ACL': 'bucket-owner-full-control', 'ServerSideEncryption': 'AES256'},
    )
