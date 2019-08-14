import csv
import datetime
import pathlib
import shutil
import tempfile
import zipfile

from anymail.message import AnymailMessage
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.dateparse import parse_date
from mtp_common.tasks import default_from_address

from credit.constants import CREDIT_STATUS
from credit.models import Credit, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from disbursement.constants import DISBURSEMENT_METHOD, DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement, LOG_ACTIONS as DISBURSEMENT_LOG_ACTIONS
from notification.rules import RULES, MonitoredRule
from transaction.utils import format_amount


class Command(BaseCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--since', help='Since date (inclusive)')
        parser.add_argument('--until', help='Until date (exclusive)')
        parser.add_argument('--rules', nargs='*', choices=RULES.keys(), help='Notification rule codes')
        parser.add_argument('emails', nargs='+', help='Email addresses to send reports to')

    def handle(self, **options):
        emails = options['emails']
        for email in emails:
            try:
                validate_email(email)
            except ValidationError:
                raise CommandError(f'"{email}" is not valid email address')

        codes = options['rules'] or RULES.keys()
        rules = [RULES[code] for code in codes]

        period_start, period_end = report_period(options['since'], options['until'])
        self.generate_reports(period_start, period_end, rules, emails)

    def generate_reports(self, period_start, period_end, rules, emails):
        period_end_inclusize = period_end - datetime.timedelta(days=1)
        if period_start == period_end_inclusize:
            period_filename = period_start.date().isoformat()
            period_description = period_start.strftime('%d %b %Y')
        else:
            period_filename = f'{period_start.date().isoformat()}-{period_end_inclusize.date().isoformat()}'
            period_description = f"{period_start.strftime('%d %b %Y')} to {period_end_inclusize.strftime('%d %b %Y')}"

        candidate_credits = Credit.objects.filter(
            prisoner_profile__isnull=False,
            sender_profile__isnull=False,
        ).filter(
            received_at__gte=period_start,
            received_at__lt=period_end,
        ).order_by('pk')
        candidate_disbursements = Disbursement.objects.filter(
            prisoner_profile__isnull=False,
            recipient_profile__isnull=False,
            resolution=DISBURSEMENT_RESOLUTION.SENT,
        ).filter(
            created__gte=period_start,
            created__lt=period_end,
        ).order_by('pk')

        bundle_path = pathlib.Path(tempfile.mkdtemp()).absolute() / period_filename
        bundle_path.mkdir(parents=True)

        try:
            for rule in rules:
                if Credit in rule.applies_to_models:
                    serialiser = CreditSerialiser(rule)
                    report_path = bundle_path / f'credits-{rule.code}.csv'
                    count = generate_report(report_path, rule, candidate_credits, serialiser)
                    if count == 0:
                        report_path.unlink()

                if Disbursement in rule.applies_to_models:
                    serialiser = DisbursementSerialiser(rule)
                    report_path = bundle_path / f'disbursements-{rule.code}.csv'
                    count = generate_report(report_path, rule, candidate_disbursements, serialiser)
                    if count == 0:
                        report_path.unlink()

            zip_path = create_zip(period_filename, bundle_path)
            if zip_path:
                send_zip(period_description, zip_path, emails)
                self.stdout.write('Emailed reports')
            else:
                self.stdout.write('No reports generated')
        finally:
            if bundle_path.exists():
                shutil.rmtree(str(bundle_path))


def make_local_datetime(date):
    return timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))


def report_period(period_start, period_end):
    if period_start:
        period_start = parse_date(period_start)
        if not period_start:
            raise CommandError('Cannot parse `--since`')
        period_start = make_local_datetime(period_start)
    if period_end:
        period_end = parse_date(period_end)
        if not period_end:
            raise CommandError('Cannot parse `--until`')
        period_end = make_local_datetime(period_end)

    today = make_local_datetime(timezone.now())
    if not period_start and not period_end:
        # default is "last week"
        period_end = today - datetime.timedelta(days=today.weekday())
        period_start = period_end - datetime.timedelta(days=7)
    elif not period_start:
        # if only end date is specified, take one day
        period_start = period_end - datetime.timedelta(days=1)
    elif not period_end:
        # if only start date is specified, take period up to today
        period_end = today

    if period_start >= period_end:
        raise CommandError('`--until` must be after `--since`')
    elif period_end > period_start + datetime.timedelta(days=7):
        raise CommandError('Maximum date span is 7 days')

    return period_start, period_end


def generate_report(report_path, rule, record_set, serialiser):
    with report_path.open('w') as f:
        writer = csv.DictWriter(f, serialiser.get_headers())
        writer.writeheader()
        count = 0
        for record in record_set:
            if rule.applies_to(record) and rule.triggered(record):
                writer.writerow(serialiser.serialise(record))
                count += 1
        return count


def create_zip(period_filename, bundle_path):
    report_paths = bundle_path.glob('*.csv')
    report_paths = filter(lambda p: p.stat().st_size > 0, report_paths)
    report_paths = sorted(report_paths)
    if not report_paths:
        return None

    zip_path = bundle_path / f'{period_filename}.zip'
    with zipfile.ZipFile(zip_path, 'w') as z:
        for path in report_paths:
            z.write(path, path.name)
    return zip_path


def send_zip(period_description, zip_file, emails):
    email = AnymailMessage(
        subject=f'Prisoner money notifications for {period_description}',
        body=f"""
OFFICIAL SENSITIVE

Please find attached, the prisoner money notifications reports for {period_description}.

If you have any queries, contact {settings.TEAM_EMAIL}.
        """.strip(),
        from_email=default_from_address(),
        to=emails,
        tags=['notifications-report'],
    )
    email.attach_file(str(zip_file), mimetype='application/zip')
    email.send()


class Serialiser:
    def __init__(self, rule):
        self.rule = rule
        self.is_monitored_rule = isinstance(rule, MonitoredRule)

    def get_headers(self):
        headers = [
            'Notification rule',
            'Internal ID',
        ]
        if self.is_monitored_rule:
            headers.insert(1, 'Monitored by')
        return headers

    def serialise(self, record):
        row = {
            'Notification rule': self.rule.description.replace('you are monitoring', 'someone monitors'),
            'Internal ID': self.get_internal_id(record),
        }
        if self.is_monitored_rule:
            row['Monitored by'] = self.rule.get_event_trigger(record).get_monitoring_users().count()
        return row

    def get_internal_id(self, record):
        raise NotImplementedError


class CreditSerialiser(Serialiser):
    def get_headers(self):
        return super().get_headers() + [
            'Date received', 'Date credited',
            'Amount',
            'Prisoner number', 'Prisoner name', 'Prison',
            'Sender name', 'Payment method',
            'Bank transfer sort code', 'Bank transfer account', 'Bank transfer roll number',
            'Debit card number', 'Debit card expiry', 'Debit card billing address',
            'Sender email', 'Sender IP address',
            'Status',
            'NOMIS transaction',
        ]

    def serialise(self, record: Credit):
        row = super().serialise(record)
        row.update({
            'Date received': format_csv_datetime(record.received_at),
            'Date credited': format_csv_datetime(find_log_date(record, CREDIT_LOG_ACTIONS.CREDITED)),
            'Amount': format_amount(record.amount),
            'Prisoner number': record.prisoner_number,
            'Prisoner name': record.prisoner_name,
            'Prison': record.prison.short_name,
            'Status': CREDIT_STATUS.for_value(record.status).display,
            'NOMIS transaction': record.nomis_transaction_id,
        })
        row.update(self.serialise_sender(record))
        return row

    def get_internal_id(self, record):
        return f'Credit {record.id}'

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
            return {
                'Payment method': 'Debit card',
                'Sender name': payment.cardholder_name,
                'Debit card number': payment.card_number_last_digits,
                'Debit card expiry': payment.card_expiry_date,
                'Debit card billing address': str(payment.billing_address),
                'Sender email': payment.email,
                'Sender IP address': payment.ip_address,
            }

        return {
            'Payment method': 'Unknown',
            'Sender name': '(Unknown sender)',
        }


class DisbursementSerialiser(Serialiser):
    def get_headers(self):
        return super().get_headers() + [
            'Date entered', 'Date confirmed', 'Date sent',
            'Amount',
            'Prisoner number', 'Prisoner name', 'Prison',
            'Recipient name', 'Payment method',
            'Bank transfer sort code', 'Bank transfer account', 'Bank transfer roll number',
            'Recipient address', 'Recipient email',
            'Status',
            'NOMIS transaction', 'SOP invoice number',
        ]

    def serialise(self, record: Disbursement):
        row = super().serialise(record)
        row.update({
            'Date entered': format_csv_datetime(record.created),
            'Date confirmed': format_csv_datetime(find_log_date(record, DISBURSEMENT_LOG_ACTIONS.CONFIRMED)),
            'Date sent': format_csv_datetime(find_log_date(record, DISBURSEMENT_LOG_ACTIONS.SENT)),
            'Amount': format_amount(record.amount),
            'Prisoner number': record.prisoner_number,
            'Prisoner name': record.prisoner_name,
            'Prison': record.prison.short_name,
            'Recipient name': record.recipient_name,
            'Payment method': DISBURSEMENT_METHOD.for_value(record.method).display,
            'Bank transfer sort code': record.sort_code,
            'Bank transfer account': record.account_number,
            'Bank transfer roll number': record.roll_number,
            'Recipient address': record.recipient_address,
            'Recipient email': record.recipient_email,
            'Status': DISBURSEMENT_RESOLUTION.for_value(record.resolution).display,
            'NOMIS transaction': record.nomis_transaction_id,
            'SOP invoice number': record.invoice_number,
        })
        return row

    def get_internal_id(self, record):
        return f'Disbursement {record.id}'


def format_csv_datetime(value):
    if not value:
        return ''
    value = timezone.localtime(value)
    return value.strftime('%Y-%m-%d %H:%M:%S')


def find_log_date(record, action):
    log = record.log_set.filter(action=action).order_by('created').first()
    return log and log.created
