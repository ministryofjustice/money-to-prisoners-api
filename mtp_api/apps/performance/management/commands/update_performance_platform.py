from datetime import datetime

from django.core.management import BaseCommand
from django.utils import timezone

from performance.updaters import registry


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--resources', nargs='*', default=list(registry.keys()),
                            choices=list(registry.keys()),
                            help='Resources to update.')
        parser.add_argument('--timestamp', default=None,
                            help='Timestamp in format Y-m-dTH:M:S')

    def handle(self, *args, **options):
        timestamp = (
            timezone.make_aware(datetime.strptime(options['timestamp'], '%Y-%m-%dT%H:%M:%S'))
            if options['timestamp'] else None
        )
        for resource in options['resources']:
            for updater in registry[resource]:
                updater(timestamp=timestamp).run()
