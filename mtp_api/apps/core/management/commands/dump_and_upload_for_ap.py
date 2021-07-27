import datetime
import os
import tempfile
import textwrap

from django.core.management import BaseCommand, call_command
from django.utils import timezone

from core.dump import Serialiser


class Command(BaseCommand):
    """
    Dump credits, disbursements, FIU-monitored prisoners, FIU-monitored debit cards and auto accept rules
    which were updated "yesterday" and upload them to an S3 bucket in Analytical Platform.
    This command is expected to be scheduled to run once per day (using core.ScheduledCommand model).
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        today = timezone.localtime().date()
        yesterday = today - datetime.timedelta(days=1)

        today = today.strftime('%Y-%m-%d')
        yesterday = yesterday.strftime('%Y-%m-%d')
        date_range = {
            'after': yesterday,
            'before': today,
        }

        with tempfile.TemporaryDirectory() as temp_path:
            for record_type in Serialiser.get_serialisers():
                file_path = os.path.join(temp_path, record_type)
                call_command('dump_for_ap', record_type, file_path, **date_range)
                call_command('upload_dump_for_ap', file_path, f'{today}_{record_type}')
