from django.conf import settings
from mtp_common.security.checks import human_readable_check_rejection_reasons
from mtp_common.utils import format_currency

from core.dump import Serialiser
from credit.constants import CreditResolution, CreditStatus, LogAction
from credit.models import Credit
from payment.constants import PaymentStatus
from payment.models import BillingAddress
from security.constants import CheckStatus


class CreditSerialiser(Serialiser):
    """
    Serialises credits which were either credited, are pending crediting or were explicitly rejected.
    Credits where money has not _yet_ been taken are not included.
    """
    record_type = 'credits'

    def __init__(self, serialise_amount_as_int=False, only_with_triggered_rules=False):
        super().__init__()
        if serialise_amount_as_int:
            self.format_amount = lambda amount: amount
        else:
            self.format_amount = format_currency
        self.only_with_triggered_rules = only_with_triggered_rules

    def get_queryset(self):
        queryset = Credit.objects_all \
            .exclude(resolution=CreditResolution.initial) \
            .exclude(payment__status=PaymentStatus.expired)
        if self.only_with_triggered_rules:
            queryset = queryset \
                .exclude(security_check__rules__len=0) \
                .exclude(security_check__rules__isnull=True)
        return queryset

    def get_headers(self):
        headers = super().get_headers() + [
            'URL',
            'Date started', 'Date received', 'Date credited',
            'Amount',
            'Status',

            'Prisoner number', 'Prisoner name', 'Prison',

            'Payment method',
            'Sender name',
        ]
        if not self.only_with_triggered_rules:
            # if only credits that triggered security rules are included, there can be no bank transfers
            headers += [
                'Bank transfer sort code', 'Bank transfer account', 'Bank transfer roll number',
            ]
        headers += [
            'Debit card first six digits', 'Debit card last four digits', 'Debit card expiry',
            'Debit card billing address line 1', 'Debit card billing address line 2', 'Debit card billing address city',
            'Debit card billing address postcode', 'Debit card billing address country',
            'Sender email', 'Sender IP address',

            'Processed by',

            'NOMIS transaction', 'WorldPay order code',

            'Security check codes', 'Security check description',
            'Security check status', 'Security check actioned by', 'Security check rejection reasons',
        ]
        return headers

    def serialise(self, record: Credit):
        status = record.status
        if status:
            status = CreditStatus[status].label
        else:
            status = 'Anonymous'

        row = super().serialise(record)
        row.update({
            'URL': f'{settings.NOMS_OPS_URL}/security/credits/{record.id}/',
            'Date received': record.received_at,
            'Date credited': record.log_set.get_action_date(LogAction.credited),
            'Amount': self.format_amount(record.amount),
            'Prisoner number': record.prisoner_number or 'Unknown',
            'Prisoner name': record.prisoner_name or 'Unknown',
            'Prison': record.prison.short_name if record.prison else 'Unknown',
            'Processed by': record.owner.username if record.owner else 'Unknown',
            'Status': status,
            'NOMIS transaction': record.nomis_transaction_id,
        })
        row.update(self.serialise_sender(record))
        row.update(self.serialise_security_check(record))
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

    def serialise_security_check(self, record: Credit):
        if hasattr(record, 'security_check'):
            security_check = record.security_check
            security_check_description = '; '.join(security_check.description)
            security_check_status = CheckStatus[security_check.status].label
            security_check_actioned_by = security_check.actioned_by.username if security_check.actioned_by else ''
            if len(security_check.rules) > 0:
                security_check_rules = security_check.rules
                security_check_rejection_reasons = '; '.join(
                    human_readable_check_rejection_reasons(security_check.rejection_reasons)
                )
            else:
                security_check_rules = None
                security_check_rejection_reasons = None
            return {
                'Security check codes': security_check_rules,
                'Security check description': security_check_description,
                'Security check status': security_check_status,
                'Security check actioned by': security_check_actioned_by,
                'Security check rejection reasons': security_check_rejection_reasons,
            }

        return {}
