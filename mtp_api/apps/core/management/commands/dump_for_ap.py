import datetime
import json
import textwrap

from django.core.management import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.dump import Serialiser


class BaseDumpCommand(BaseCommand):
    """
    Abstract base class for data dumping
    """

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--after', help='Modified after date (inclusive)')
        parser.add_argument('--before', help='Modified before date (exclusive)')
        parser.add_argument('type', choices=list(Serialiser.get_serialisers()), help='Type of object to dump')
        parser.add_argument('path', help='Path to dump data to')

    @classmethod
    def get_modified_range(cls, **options):
        after = date_argument(options['after'])
        before = date_argument(options['before'])
        if after and before and before <= after:
            raise CommandError('"--before" must be after "--after"')
        return after, before


def date_argument(argument):
    if not argument:
        return None
    date = parse_date(argument)
    if not date:
        raise CommandError('Cannot parse date')
    return timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))


class Command(BaseDumpCommand):
    """
    Dump data for Analytical Platform
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        after, before = self.get_modified_range(**options)
        record_type = options['type']
        serialiser: Serialiser = Serialiser.get_serialisers()[record_type]()
        records = serialiser.get_modified_records(after, before)

        self.stdout.write(f'Dumping {record_type} records for Analytical Platform export')

        with open(options['path'], 'wt') as jsonl_file:
            for record in records:
                jsonl_file.write(json.dumps(serialiser.serialise(record), default=str, ensure_ascii=False))
                jsonl_file.write('\n')
