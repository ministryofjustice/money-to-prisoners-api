from django.db.transaction import atomic

from credit.models import Credit
from disbursement.models import Disbursement
from notification.models import (
    Event, CreditEvent, DisbursementEvent,
    SenderProfileEvent, RecipientProfileEvent, PrisonerProfileEvent,
)
from security.models import SenderProfile, RecipientProfile, PrisonerProfile
from transaction.utils import format_amount

ENABLED_RULE_CODES = {'MONP', 'MONS'}


def create_notification_events(record):
    for code in ENABLED_RULE_CODES:
        rule = RULES[code]
        if rule.applies_to(record) and rule.triggered(record):
            rule.create_events(record)


class BaseRule:
    applies_to_models = (Credit, Disbursement)

    def __init__(self, code, description, abbr_description, applies_to_models=None, **kwargs):
        self.code = code
        self.description = description
        self.abbr_description = abbr_description
        self.kwargs = kwargs
        if applies_to_models:
            self.applies_to_models = applies_to_models

    def applies_to(self, record):
        return isinstance(record, self.applies_to_models)

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
    def __init__(self, *args, limit, **kwargs):
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
        if profile and profile.get_monitoring_users().exists():
            return True
        return False

    def get_event_trigger(self, record):
        return getattr(record, self.kwargs['profile'])


RULES = {
    # rules used for generating notification events for users of noms-ops
    'MONP': MonitoredRule(
        'MONP',
        description='Credits or disbursements for prisoners you are monitoring',
        abbr_description='mon. prisoners',
        profile='prisoner_profile',
    ),
    'MONS': MonitoredRule(
        'MONS',
        description='Credits for payment sources you are monitoring',
        abbr_description='mon. sources',
        applies_to_models=(Credit,),
        profile='sender_profile',
    ),

    # rules used only in specially-generated notification reports
    'MONR': MonitoredRule(
        'MONR',
        description='Disbursements for recipients you are monitoring',
        abbr_description='mon. recipients',
        applies_to_models=(Disbursement,),
        profile='recipient_profile',
    ),
    'NWN': NotWholeNumberRule(
        'NWN',
        description='Credits or disbursements that are not a whole number',
        abbr_description='not whole',
    ),
    'HA': HighAmountRule(
        'HA',
        description='Credits or disbursements over {display_limit}',
        abbr_description='high amount',
        limit=12000,
    ),
}
