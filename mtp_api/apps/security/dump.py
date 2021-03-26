from django.conf import settings

from core.dump import Serialiser
from security.models import DebitCardSenderDetails, PrisonerProfile, CheckAutoAcceptRule, CheckAutoAcceptRuleState


class FIUMonitoredDebitCardsSerialiser(Serialiser):
    """
    Serialises debit cards that are monitored by FIU
    """
    record_type = 'fiu_senders_debit_cards'

    def get_queryset(self):
        return DebitCardSenderDetails.objects.filter(monitoring_users__groups__name='FIU').distinct()

    def serialise(self, record: DebitCardSenderDetails):
        return {
            'Exported at': self.exported_at_local_time,
            'Internal ID': record.id,
            'URL': f'{settings.NOMS_OPS_URL}/security/senders/{record.sender_id}/',
            'Debit card last four digits': record.card_number_last_digits,
            'Debit card expiry': record.card_expiry_date,
            'Debit card billing address postcode': record.postcode,
        }


class FIUMonitoredPrisonerSerialiser(Serialiser):
    """
    Serialises prisoners that are monitored by FIU
    """
    record_type = 'fiu_prisoners'

    def get_queryset(self):
        return PrisonerProfile.objects.filter(monitoring_users__groups__name='FIU').distinct()

    def serialise(self, record: PrisonerProfile):
        return {
            'Exported at': self.exported_at_local_time,
            'Internal ID': record.id,
            'URL': f'{settings.NOMS_OPS_URL}/security/prisoners/{record.id}/',
            'Prisoner number': record.prisoner_number,
            'Prisoner name': record.prisoner_name,
            'Prison': record.current_prison.short_name if record.current_prison else '',
        }


class AutoAcceptSerialiser(Serialiser):
    """
    Serialises prisoner↔︎debit card relationships where credits are automatically accepted
    without FIU intervention, or _used_ to be automatically accepted.
    """
    record_type = 'auto_accepts'

    def get_queryset(self):
        return CheckAutoAcceptRule.objects.filter()

    def serialise(self, record: CheckAutoAcceptRule):
        state: CheckAutoAcceptRuleState = record.get_latest_state()
        debit_card_sender_details = record.debit_card_sender_details
        prisoner_profile = record.prisoner_profile
        return {
            'Exported at': self.exported_at_local_time,
            'Internal ID': record.id,
            'Status': 'Active' if state.active else 'Inactive',
            'Reason': state.reason,
            'Updated by username': state.added_by.username if state.added_by else 'Unknown',
            'URL': f'{settings.NOMS_OPS_URL}/security/checks/auto-accept-rules/{record.id}/',
            'Sender profile URL': f'{settings.NOMS_OPS_URL}/security/senders/{debit_card_sender_details.sender_id}/',
            'Debit card last four digits': debit_card_sender_details.card_number_last_digits,
            'Debit card expiry': debit_card_sender_details.card_expiry_date,
            'Debit card billing address postcode': debit_card_sender_details.postcode,
            'Prisoner profile URL': f'{settings.NOMS_OPS_URL}/security/prisoners/{record.id}/',
            'Prisoner number': prisoner_profile.prisoner_number,
            'Prisoner name': prisoner_profile.prisoner_name,
            'Prison': prisoner_profile.current_prison.short_name if prisoner_profile.current_prison else '',
        }
