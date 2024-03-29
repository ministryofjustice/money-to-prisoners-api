from django.conf import settings
from mtp_common.utils import format_currency

from core.dump import Serialiser
from disbursement.constants import DisbursementResolution, DisbursementMethod, LogAction
from disbursement.models import Disbursement


class DisbursementSerialiser(Serialiser):
    """
    Serialises all disbursements, including those that were cancelled.
    """
    record_type = 'disbursements'

    def __init__(self, serialise_amount_as_int=False):
        super().__init__()
        if serialise_amount_as_int:
            self.format_amount = lambda amount: amount
        else:
            self.format_amount = format_currency

    def get_queryset(self):
        return Disbursement.objects.all()

    def get_headers(self):
        return super().get_headers() + [
            'URL',
            'Date entered', 'Date confirmed', 'Date sent',
            'Amount',
            'Prisoner number', 'Prisoner name', 'Prison',
            'Recipient first name', 'Recipient last name',
            'Payment method',
            'Bank transfer sort code', 'Bank transfer account', 'Bank transfer roll number',
            'Recipient address line 1', 'Recipient address line 2', 'Recipient address city',
            'Recipient address postcode', 'Recipient address country',
            'Recipient email',
            'Status',
            'NOMIS transaction', 'SOP invoice number',
        ]

    def serialise(self, record: Disbursement):
        row = super().serialise(record)
        row.update({
            'URL': f'{settings.NOMS_OPS_URL}/security/disbursements/{record.id}/',
            'Date entered': record.created,
            'Date confirmed': record.log_set.get_action_date(LogAction.confirmed),
            'Date sent': record.log_set.get_action_date(LogAction.sent),
            'Amount': self.format_amount(record.amount),
            'Prisoner number': record.prisoner_number,
            'Prisoner name': record.prisoner_name,
            'Prison': record.prison.short_name,
            'Recipient first name': record.recipient_first_name,
            'Recipient last name': record.recipient_last_name,
            'Payment method': DisbursementMethod[record.method].label,
            'Bank transfer sort code': record.sort_code,
            'Bank transfer account': record.account_number,
            'Bank transfer roll number': record.roll_number,
            'Recipient address line 1': record.address_line1,
            'Recipient address line 2': record.address_line2,
            'Recipient address city': record.city,
            'Recipient address postcode': record.postcode,
            'Recipient address country': record.country,
            'Recipient email': record.recipient_email,
            'Status': DisbursementResolution[record.resolution].label,
            'NOMIS transaction': record.nomis_transaction_id,
            'SOP invoice number': record.invoice_number,
        })
        return row
