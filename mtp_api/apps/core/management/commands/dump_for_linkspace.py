import csv
import json
import textwrap

from core.dump import Serialiser
from core.management.commands.dump_for_ap import BaseDumpCommand


class Command(BaseDumpCommand):
    """
    Dump data for Linkspace
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        super().add_arguments(parser)
        record_types = ['credits', 'fiu_senders_debit_cards', 'fiu_prisoners', 'auto_accepts']
        parser.add_argument('--format', choices=['csv', 'json'], default='csv', help='File format to use for dump')
        parser.add_argument('type', choices=record_types, help='Type of object to dump')
        parser.add_argument('path', help='Path to dump data to')

    def handle(self, *args, **options):
        after, before = self.get_modified_range(**options)
        serialiser = get_serialiser(options['type'])
        records = serialiser.get_modified_records(after, before)
        if options['format'] == 'json':
            self.serialise_as_json(serialiser, records, options['path'])
        else:
            self.serialise_as_csv(serialiser, records, options['path'])

    @classmethod
    def serialise_as_csv(cls, serialiser, records, path):
        with open(path, 'wt') as csv_file:
            writer = csv.DictWriter(csv_file, serialiser.get_headers())
            writer.writeheader()
            for record in records:
                writer.writerow(serialiser.serialise(record))

    @classmethod
    def serialise_as_json(cls, serialiser, records, path):
        with open(path, 'wt') as json_file:
            json_file.write('[\n')
            records_written = False
            for record in records:
                if records_written:
                    json_file.write(',\n')
                data = serialiser.serialise(record)
                json.dump(data, json_file, default=str, ensure_ascii=False)
                records_written = True
            json_file.write('\n]\n')


def get_serialiser(record_type) -> Serialiser:
    from credit.dump import CreditSerialiser

    serialiser_cls = Serialiser.get_serialisers()[record_type]
    if issubclass(serialiser_cls, CreditSerialiser):
        return serialiser_cls(serialise_amount_as_int=True, only_with_triggered_rules=True)
    return serialiser_cls()
