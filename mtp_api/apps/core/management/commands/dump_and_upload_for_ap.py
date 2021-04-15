import datetime
import pathlib
import tempfile
import textwrap

from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    """
    Dump credits and disbursements updated "yesterday" and upload them to an S3 bucket in Analytical Platform.
    This command is expected to be scheduled to run once per day (using core.ScheduledCommand model).
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        with tempfile.TemporaryDirectory() as temp_path:

            file_path_credits = pathlib.Path(temp_path) / 'credits'
            file_path_disbursements = pathlib.Path(temp_path) / 'disbursements'

            date = todays_date()

            dump_for_ap_command(str(file_path_credits), str(file_path_disbursements))
            upload_dump_for_ap_command(str(file_path_credits), str(file_path_disbursements), date)


def dump_for_ap_command(file_path_credits, file_path_disbursements):
    yesterday = yesterdays_date()
    today = todays_date()

    call_command('dump_for_ap', 'credits', file_path_credits, after=yesterday, before=today)
    call_command('dump_for_ap', 'disbursements', file_path_disbursements, after=yesterday, before=today)


def upload_dump_for_ap_command(file_path_credits, file_path_disbursements, date):
    call_command('upload_dump_for_ap', file_path_credits, (f'{date}_credits'))
    call_command('upload_dump_for_ap', file_path_disbursements, (f'{date}_disbursements'))


def todays_date():
    return datetime.date.today().strftime('%Y-%m-%d')


def yesterdays_date():
    date = datetime.date.today() - datetime.timedelta(days=1)
    return date.strftime('%Y-%m-%d')
