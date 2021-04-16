from django.conf import settings

from core.dump import Serialiser
from credit.constants import CREDIT_RESOLUTION, CREDIT_STATUS
from credit.models import Credit, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from payment.models import PAYMENT_STATUS, BillingAddress
from security.models import CHECK_STATUS
from transaction.utils import format_amount


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
            self.format_amount = format_amount
        self.only_with_triggered_rules = only_with_triggered_rules

    def get_queryset(self):
        queryset = Credit.objects_all \
            .exclude(resolution=CREDIT_RESOLUTION.INITIAL) \
            .exclude(payment__status=PAYMENT_STATUS.EXPIRED)
        if self.only_with_triggered_rules:
            queryset = queryset \
                .exclude(security_check__rules__len=0) \
                .exclude(security_check__rules__isnull=True)
        return queryset

    def serialise(self, record: Credit):
        status = record.status
        if status:
            status = CREDIT_STATUS.for_value(status).display
        else:
            status = 'Anonymous'

        if hasattr(record, 'security_check'):
            security_check_description = ' '.join(record.security_check.description)
            security_check_status = CHECK_STATUS.for_value(record.security_check.status).display
            if len(record.security_check.rules) > 0:
                security_check_rules = record.security_check.rules
                security_check_rejection_reasons = record.security_check.rejection_reasons
            else:
                security_check_rules = None
                security_check_rejection_reasons = None
        else:
            security_check_description = None
            security_check_status = None
            security_check_rules = None
            security_check_rejection_reasons = None

        row = {
            'Exported at': self.exported_at_local_time,
            'Internal ID': record.id,
            'URL': f'{settings.NOMS_OPS_URL}/security/credits/{record.id}/',
            'Date received': record.received_at,
            'Date credited': record.log_set.get_action_date(CREDIT_LOG_ACTIONS.CREDITED),
            'Amount': self.format_amount(record.amount),
            'Prisoner number': record.prisoner_number or 'Unknown',
            'Prisoner name': record.prisoner_name or 'Unknown',
            'Prison': record.prison.short_name if record.prison else 'Unknown',
            # TODO: check with analytical platform and fiu whether this is needed and
            #   then rename to something like "Processed by":
            'Owner username': record.owner.username if record.owner else 'Unknown',
            # TODO: this field is not useful and misleading.
            #  it applies ONLY to bank transfers that did not have sufficient sender details (no longer possible).
            #  check with analytical platform and fiu before removing:
            'Blocked': record.blocked,
            'Status': status,
            'NOMIS transaction': record.nomis_transaction_id,
            'Security check codes': security_check_rules,
            'Security check description': security_check_description,
            'Security check status': security_check_status,
            'Security check rejection reasons': security_check_rejection_reasons,
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
