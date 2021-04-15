from django.conf import settings

from core.dump import Serialiser
from disbursement.constants import DISBURSEMENT_METHOD, DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement, LOG_ACTIONS as DISBURSEMENT_LOG_ACTIONS
from transaction.utils import format_amount


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
            self.format_amount = format_amount

    def get_queryset(self):
        return Disbursement.objects.all()

    def serialise(self, record: Disbursement):
        return {
            'Exported at': self.exported_at_local_time,
            'Internal ID': record.id,
            'URL': f'{settings.NOMS_OPS_URL}/security/disbursements/{record.id}/',
            'Date entered': record.created,
            'Date confirmed': record.log_set.get_action_date(DISBURSEMENT_LOG_ACTIONS.CONFIRMED),
            'Date sent': record.log_set.get_action_date(DISBURSEMENT_LOG_ACTIONS.SENT),
            'Amount': self.format_amount(record.amount),
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
