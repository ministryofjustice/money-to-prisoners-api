from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _

from credit.models import Credit
from disbursement.models import Disbursement
from notification.models import (
    Event, CreditEvent, DisbursementEvent,
    SenderProfileEvent, RecipientProfileEvent, PrisonerProfileEvent,
)
from security.models import SenderProfile, RecipientProfile, PrisonerProfile
from transaction.utils import format_amount

ENABLED_CREDIT_RULES = ['MONP', 'MONS']
ENABLED_DISBURSEMENT_RULES = ['MONP']
ENABLED_RULES = set(ENABLED_CREDIT_RULES) | set(ENABLED_DISBURSEMENT_RULES)


def create_credit_notifications(credit):
    for rule in ENABLED_CREDIT_RULES:
        rule = RULES[rule]
        if rule.triggered(credit):
            rule.create_events(credit)


def create_disbursement_notifications(disbursement):
    for rule in ENABLED_DISBURSEMENT_RULES:
        rule = RULES[rule]
        if rule.triggered(disbursement):
            rule.create_events(disbursement)


class BaseRule:
    def __init__(self, code, description, **kwargs):
        self.code = code
        self._description = description
        self.kwargs = kwargs

    @property
    def description(self):
        display_kwargs = self.kwargs.copy()
        return self._description.format(**display_kwargs)

    def triggered(self, record):
        raise NotImplementedError

    def get_event_trigger(self, record):
        return record

    def create_event(self, record, user=None):
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
        return [self.create_event(record)]


class NotWholeNumberRule(BaseRule):
    def triggered(self, record):
        return record.amount % 100


class HighAmountRule(BaseRule):
    def __init__(self, *args, limit=12000):
        super().__init__(*args, limit=limit)
        self.kwargs['display_limit'] = format_amount(limit, trim_empty_pence=True, pound_sign=True)

    def triggered(self, record):
        return record.amount >= self.kwargs['limit']


class MonitoredRule(BaseRule):
    @atomic
    def create_events(self, record):
        profile = self.get_event_trigger(record)
        return [
            self.create_event(record, user=user)
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
        _('Credits or disbursements for prisoners you are monitoring'),
        profile='prisoner_profile',
    ),
    'MONS': MonitoredRule(
        'MONS',
        _('Credits for senders you are monitoring'),
        profile='sender_profile',
    ),
    # disabled rules
    'MONR': MonitoredRule(
        'MONR',
        _('Disbursements for recipients you are monitoring'),
        profile='recipient_profile',
    ),
    'NWN': NotWholeNumberRule(
        'NWN',
        _('Credits or disbursements that are not a whole number'),
    ),
    'HA': HighAmountRule(
        'HA',
        'Credits or disbursements over {display_limit}',
    ),
}
