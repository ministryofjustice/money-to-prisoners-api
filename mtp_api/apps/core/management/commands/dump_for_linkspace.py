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
            writer = csv.DictWriter(csv_file, cls.get_headers_for_linkspace(serialiser))
            writer.writeheader()
            for record in records:
                writer.writerow(cls.get_data_for_linkspace(serialiser, record))

    @classmethod
    def serialise_as_json(cls, serialiser, records, path):
        with open(path, 'wt') as json_file:
            json_file.write('[\n')
            records_written = False
            for record in records:
                if records_written:
                    json_file.write(',\n')
                data = cls.get_data_for_linkspace(serialiser, record)
                json.dump(data, json_file, default=str, ensure_ascii=False)
                records_written = True
            json_file.write('\n]\n')

    @classmethod
    def get_headers_for_linkspace(cls, serialiser):
        headers = serialiser.get_headers()
        return [
            cls.short_name_for(serialiser.record_type, column_name)
            for column_name in headers
        ]

    @classmethod
    def get_data_for_linkspace(cls, serialiser, record):
        data = serialiser.serialise(record)
        return {
            cls.short_name_for(serialiser.record_type, column_name): value
            for column_name, value in data.items()
        }

    @classmethod
    def short_name_for(cls, record_type, column_name):
        linkspace_short_names_mapping = {
            # Common fields
            'Created at': 'created_at',
            'Modified at': 'modified_at',
            'Exported at': 'exported_at',
            'Internal ID': 'internal_id',
            # Other fields (alphabetical order)
            'Amount': 'amount',
            'Bank transfer account': 'bank_transfer_account',
            'Bank transfer roll number': 'bank_transfer_roll_number',
            'Bank transfer sort code': 'bank_transfer_sort_code',
            'Date credited': 'date_created',
            'Date received': 'date_received',
            'Date started': 'date_started',
            'Debit card billing address city': 'debit_card_billing_address_city',
            'Debit card billing address country': 'debit_card_billing_address_country',
            'Debit card billing address line 1': 'debit_card_billing_address_line_1',
            'Debit card billing address line 2': 'debit_card_billing_address_line_2',
            'Debit card billing address postcode': 'debit_card_billing_address_postcode',
            'Debit card expiry': 'debit_card_expiry',
            'Debit card first six digits': 'debit_card_last_6_digits',
            'Debit card last four digits': 'debit_card_last_4_digits',
            'NOMIS transaction': 'nomis_transaction',
            'Payment method': 'payment_method',
            'Prison': 'prison',
            'Prisoner name': 'prisoner_name',
            'Prisoner number': 'prisoner_number',
            'Prisoner profile URL': 'prisoner_profile_url',
            'Processed by': 'processed_by',
            'Reason': 'reason',
            'Security check actioned by': 'security_check_actioned_by',
            'Security check codes': 'security_check_codes',
            'Security check description': 'security_check_description',
            'Security check rejection reasons': 'security_check_rejection_reasons',
            'Security check status': 'security_check_status',
            'Sender email': 'sender_email',
            'Sender IP address': 'sender_ip_address',
            'Sender name': 'sender_name',
            'Sender profile URL': 'sender_profile_url',
            'Status': 'status',
            'Updated by': 'updated_by',
            'URL': 'url',
            'WorldPay order code': 'worldpay_order_code',
        }

        # Prefixing with record type because LinkSpace short codes are unique across all the tables
        return record_type + '_' + linkspace_short_names_mapping[column_name]


def get_serialiser(record_type) -> Serialiser:
    from credit.dump import CreditSerialiser

    serialiser_cls = Serialiser.get_serialisers()[record_type]
    if issubclass(serialiser_cls, CreditSerialiser):
        return serialiser_cls(serialise_amount_as_int=True, only_with_triggered_rules=True)
    return serialiser_cls()
