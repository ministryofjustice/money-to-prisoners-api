from django.db.transaction import atomic

from credit.models import Credit
from disbursement.models import Disbursement
from notification.models import (
    Event, CreditEvent, DisbursementEvent,
    SenderProfileEvent, RecipientProfileEvent, PrisonerProfileEvent,
)
from security.models import SenderProfile, RecipientProfile, PrisonerProfile
from transaction.utils import format_amount

ENABLED_CREDIT_RULE_CODES = ['MONP', 'MONS']
ENABLED_DISBURSEMENT_RULE_CODES = ['MONP']
ENABLED_RULE_CODES = set(ENABLED_CREDIT_RULE_CODES) | set(ENABLED_DISBURSEMENT_RULE_CODES)


def create_credit_notifications(credit):
    for rule in ENABLED_CREDIT_RULE_CODES:
        rule = RULES[rule]
        if rule.triggered(credit):
            rule.create_events(credit)


def create_disbursement_notifications(disbursement):
    for rule in ENABLED_DISBURSEMENT_RULE_CODES:
        rule = RULES[rule]
        if rule.triggered(disbursement):
            rule.create_events(disbursement)


class BaseRule:
    def __init__(self, code, description, **kwargs):
        self.code = code
        self.description = description
        self.kwargs = kwargs

    def triggered(self, record):
        raise NotImplementedError

    def get_event_trigger(self, record):
        return record

    def _create_event(self, record, user=None):
        event_relations = []
        event = Event(rule=self.code, description=self.description, user=user)
        if isinstance(record, Credit):
            event.triggered_at = record.received_at
            event.save()
            event_relations.append(CreditEvent(event=event, credit=record))
        elif isinstance(record, Disbursement):
            event.triggered_at = record.created
            event.save()
            event_relations.append(DisbursementEvent(event=event, disbursement=record))
        else:
            return

        trigger = self.get_event_trigger(record)
        if trigger and trigger != record:
            if isinstance(trigger, SenderProfile):
                event_relations.append(
                    SenderProfileEvent(event=event, sender_profile=trigger)
                )
            elif isinstance(trigger, RecipientProfile):
                event_relations.append(
                    RecipientProfileEvent(event=event, recipient_profile=trigger)
                )
            elif isinstance(trigger, PrisonerProfile):
                event_relations.append(
                    PrisonerProfileEvent(event=event, prisoner_profile=trigger)
                )

        for event_relation in event_relations:
            event_relation.save()

        return event

    @atomic
    def create_events(self, record):
        return [self._create_event(record)]


class NotWholeNumberRule(BaseRule):
    def triggered(self, record):
        return bool(record.amount % 100)


class HighAmountRule(BaseRule):
    def __init__(self, *args, limit=12000, **kwargs):
        kwargs['limit'] = limit
        super().__init__(*args, **kwargs)
        self.description = self.description.format(
            display_limit=format_amount(limit, trim_empty_pence=True, pound_sign=True)
        )

    def triggered(self, record):
        return record.amount >= self.kwargs['limit']


class MonitoredRule(BaseRule):
    @atomic
    def create_events(self, record):
        profile = self.get_event_trigger(record)
        return [
            self._create_event(record, user=user)
            for user in profile.get_monitoring_users().all()
        ]

    def triggered(self, record):
        profile = self.get_event_trigger(record)
        if profile and profile.get_monitoring_users().count():
            return True
        return False

    def get_event_trigger(self, record):
        return getattr(record, self.kwargs['profile'])


RULES = {
    'MONP': MonitoredRule(
        'MONP',
        'Credits or disbursements for prisoners you are monitoring',
        profile='prisoner_profile',
    ),
    'MONS': MonitoredRule(
        'MONS',
        'Credits for senders you are monitoring',
        profile='sender_profile',
    ),
    # disabled rules
    'MONR': MonitoredRule(
        'MONR',
        'Disbursements for recipients you are monitoring',
        profile='recipient_profile',
    ),
    'NWN': NotWholeNumberRule(
        'NWN',
        'Credits or disbursements that are not a whole number',
    ),
    'HA': HighAmountRule(
        'HA',
        'Credits or disbursements over {display_limit}',
    ),
}
