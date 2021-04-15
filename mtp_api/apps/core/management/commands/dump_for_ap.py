import datetime
import json
import textwrap

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from credit.constants import CREDIT_STATUS
from credit.models import Credit, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from disbursement.constants import DISBURSEMENT_METHOD, DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement, LOG_ACTIONS as DISBURSEMENT_LOG_ACTIONS
from payment.models import BillingAddress
from transaction.utils import format_amount


class Command(BaseCommand):
    """
    Dump data for Analytical Platform
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--after', help='Modified after date (inclusive)')
        parser.add_argument('--before', help='Modified before date (exclusive)')
        parser.add_argument('type', choices=list(Serialiser.serialisers), help='Type of object to dump')
        parser.add_argument('path', help='Path to dump data to')

    def handle(self, *args, **options):
        after = date_argument(options['after'])
        before = date_argument(options['before'])
        if after and before and before <= after:
            raise CommandError('"--before" must be after "--after"')

        record_type = options['type']
        serialiser: Serialiser = Serialiser.serialisers[record_type]()

        with open(options['path'], 'wt') as jsonl_file:
            records = serialiser.get_modified_records(after, before)

            for record in records:
                jsonl_file.write(json.dumps(serialiser.serialise(record), default=str, ensure_ascii=False))
                jsonl_file.write('\n')


class Serialiser:
    serialisers = {}
    serialised_model = None

    def __init_subclass__(cls, serialised_model):
        record_type = str(serialised_model._meta.verbose_name_plural)
        cls.serialisers[record_type] = cls
        cls.serialised_model = serialised_model

    def __init__(self):
        self.exported_at_local_time = timezone.now()

    def get_modified_records(self, after, before):
        filters = {}
        if after:
            filters['modified__gte'] = after
        if before:
            filters['modified__lt'] = before
        # TODO should we include rejected and expired credits as well?
        return self.serialised_model.objects.filter(**filters).order_by('pk').iterator(chunk_size=1000)

    def serialise(self, record):
        raise NotImplementedError


class CreditSerialiser(Serialiser, serialised_model=Credit):
    def serialise(self, record: Credit):
        status = record.status
        if status:
            status = CREDIT_STATUS.for_value(status).display
        else:
            status = 'Anonymous'

        if hasattr(record, 'security_check'):
            security_check_status = record.security_check.status
            if len(record.security_check.rules) > 0:
                security_check_rules = record.security_check.rules
            else:
                security_check_rules = None
        else:
            security_check_status = None
            security_check_rules = None

        row = {
            'Exported at': self.exported_at_local_time,
            'Internal ID': record.id,
            'URL': f'{settings.NOMS_OPS_URL}/security/credits/{record.id}/',
            'Date received': record.received_at,
            'Date credited': record.log_set.get_action_date(CREDIT_LOG_ACTIONS.CREDITED),
            'Amount': format_amount(record.amount),
            'Prisoner number': record.prisoner_number or 'Unknown',
            'Prisoner name': record.prisoner_name or 'Unknown',
            'Prison': record.prison.short_name if record.prison else 'Unknown',
            'Owner username': record.owner.username if record.owner else 'Unknown',
            'Blocked': record.blocked,
            'Status': status,
            'NOMIS transaction': record.nomis_transaction_id,
            'Security check status': security_check_status,
            'Security check codes': security_check_rules,
            **self.serialise_sender(record)
        }
        return row

    def serialise_sender(self, record: Credit):
        if hasattr(record, 'transaction'):
            transaction = record.transaction
            return {
                'Payment method': 'Bank transfer',
                'Sender name': transaction.sender_name,
                'Bank transfer sort code': transaction.sender_sort_code,
                'Bank transfer account': transaction.sender_account_number,
                'Bank transfer roll number': transaction.sender_roll_number,
            }

        if hasattr(record, 'payment'):
            payment = record.payment
            billing_address = payment.billing_address
            if not billing_address:
                billing_address = BillingAddress()
            return {
                'Date started': payment.created,
                'Payment method': 'Debit card',
                'Sender name': payment.cardholder_name,
                'Debit card first six digits': payment.card_number_first_digits or 'Unknown',
                'Debit card last four digits': payment.card_number_last_digits,
                'Debit card expiry': payment.card_expiry_date,
                'Debit card billing address line 1': billing_address.line1,
                'Debit card billing address line 2': billing_address.line2,
                'Debit card billing address city': billing_address.city,
                'Debit card billing address postcode': billing_address.postcode,
                'Debit card billing address country': billing_address.country,
                'Sender email': payment.email,
                'Sender IP address': payment.ip_address,
                'WorldPay order code': payment.worldpay_id,
            }

        return {
            'Payment method': 'Unknown',
            'Sender name': '(Unknown sender)',
        }


class DisbursementSerialiser(Serialiser, serialised_model=Disbursement):
    def serialise(self, record: Disbursement):
        return {
            'Exported at': self.exported_at_local_time,
            'Internal ID': record.id,
            'URL': f'{settings.NOMS_OPS_URL}/security/disbursements/{record.id}/',
            'Date entered': record.created,
            'Date confirmed': record.log_set.get_action_date(DISBURSEMENT_LOG_ACTIONS.CONFIRMED),
            'Date sent': record.log_set.get_action_date(DISBURSEMENT_LOG_ACTIONS.SENT),
            'Amount': format_amount(record.amount),
            'Prisoner number': record.prisoner_number,
            'Prisoner name': record.prisoner_name,
            'Prison': record.prison.short_name,
            'Recipient first name': record.recipient_first_name,
            'Recipient last name': record.recipient_last_name,
            'Payment method': DISBURSEMENT_METHOD.for_value(record.method).display,
            'Bank transfer sort code': record.sort_code,
            'Bank transfer account': record.account_number,
            'Bank transfer roll number': record.roll_number,
            'Recipient address line 1': record.address_line1,
            'Recipient address line 2': record.address_line2,
            'Recipient address city': record.city,
            'Recipient address postcode': record.postcode,
            'Recipient address country': record.country,
            'Recipient email': record.recipient_email,
            'Status': DISBURSEMENT_RESOLUTION.for_value(record.resolution).display,
            'NOMIS transaction': record.nomis_transaction_id,
            'SOP invoice number': record.invoice_number,
        }


def date_argument(argument):
    if not argument:
        return None
    date = parse_date(argument)
    if not date:
        raise CommandError('Cannot parse date')
    return timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))
