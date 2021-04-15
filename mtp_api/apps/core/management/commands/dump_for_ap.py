import datetime
import json
import textwrap

from django.core.management import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.dump import Serialiser


class Command(BaseCommand):
    """
    Dump data for Analytical Platform
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--after', help='Modified after date (inclusive)')
        parser.add_argument('--before', help='Modified before date (exclusive)')
        parser.add_argument('type', choices=list(Serialiser.get_serialisers()), help='Type of object to dump')
        parser.add_argument('path', help='Path to dump data to')

    def handle(self, *args, **options):
        after = date_argument(options['after'])
        before = date_argument(options['before'])
        if after and before and before <= after:
            raise CommandError('"--before" must be after "--after"')

        record_type = options['type']
        serialiser: Serialiser = Serialiser.get_serialisers()[record_type]()

        with open(options['path'], 'wt') as jsonl_file:
            records = serialiser.get_modified_records(after, before)

            for record in records:
                jsonl_file.write(json.dumps(serialiser.serialise(record), default=str, ensure_ascii=False))
                jsonl_file.write('\n')


def date_argument(argument):
    if not argument:
        return None
    date = parse_date(argument)
    if not date:
        raise CommandError('Cannot parse date')
    return timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))
