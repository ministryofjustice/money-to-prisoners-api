import datetime
import os
import tempfile
import textwrap

from django.core.management import BaseCommand, call_command
from django.utils import timezone


class Command(BaseCommand):
    """
    Dump credits, FIU-monitored prisoners, FIU-monitored debit cards and auto accept rules
    which were updated "yesterday" and upload them to LinkSpace.
    This command is expected to be scheduled to run once per day (using core.ScheduledCommand model).
    """
    help = textwrap.dedent(__doc__).strip()

    linkspace_tables = {
        'credits': 'fiucredits',
        'fiu_senders_debit_cards': 'fiudebit',
        'fiu_prisoners': 'fiuprisoner',
        'auto_accepts': 'fiuauto',
    }

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
            for record_type, table_name in self.linkspace_tables.items():
                file_path = os.path.join(temp_path, record_type)
                call_command('dump_for_linkspace', record_type, file_path, format='json', **date_range)
                call_command('upload_dump_for_linkspace', file_path, table_name)
