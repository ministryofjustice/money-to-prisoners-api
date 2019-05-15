from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _

from credit.models import Credit
from disbursement.models import Disbursement
from notification.models import (
    Event, CreditEvent, DisbursementEvent, SenderProfileEvent,
    RecipientProfileEvent, PrisonerProfileEvent
)
from security.models import SenderProfile, RecipientProfile, PrisonerProfile
from security.constants import TIME_PERIOD

CREDIT_RULES = ['MONP', 'MONS', 'NWN', 'HA', 'CSFREQ', 'CSNUM', 'CPNUM']
DISBURSEMENT_RULES = ['MONP', 'MONR', 'NWN', 'HA', 'DRFREQ', 'DRNUM', 'DPNUM']


def create_credit_notifications(credit):
    for rule in CREDIT_RULES:
        if RULES[rule].triggered(credit):
            RULES[rule].create_events(credit)


def create_disbursement_notifications(disbursement):
    for rule in DISBURSEMENT_RULES:
        if RULES[rule].triggered(disbursement):
            RULES[rule].create_events(disbursement)


class BaseRule:

    def __init__(self, code, description, **kwargs):
        self.code = code
        self._description = description
        self.kwargs = kwargs

    @property
    def description(self):
        display_kwargs = self.kwargs.copy()
        if 'time_period' in display_kwargs:
            display_kwargs['time_period'] = TIME_PERIOD.for_value(
                display_kwargs['time_period']
            ).display
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


class TotalsRule(BaseRule):

    def __init__(self, *args, total, profile, limit, time_period):
        super().__init__(
            *args, total=total, profile=profile, limit=limit, time_period=time_period
        )

    def triggered(self, record):
        profile = self.get_event_trigger(record)
        if isinstance(profile, SenderProfile):
            try:
                if profile == SenderProfile.objects.get_anonymous_sender():
                    return False
            except SenderProfile.DoesNotExist:
                pass
        elif isinstance(profile, RecipientProfile):
            try:
                if profile == RecipientProfile.objects.get_cheque_recipient():
                    return False
            except RecipientProfile.DoesNotExist:
                pass

        if profile:
            totals = profile.totals.get(time_period=self.kwargs['time_period'])
            if getattr(totals, self.kwargs['total']) >= self.kwargs['limit']:
                return True
        return False

    def get_event_trigger(self, record):
        return getattr(record, self.kwargs['profile'])


class NotWholeNumberRule(BaseRule):

    def triggered(self, record):
        return record.amount % 100


class HighAmountRule(BaseRule):

    def __init__(self, *args, limit=12000):
        super().__init__(*args, limit=limit)

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
        'Credits or disbursements over £{limit}',
    ),
    'CSFREQ': TotalsRule(
        'CSFREQ',
        _(
            'More than {limit} credits from the same debit '
            'card or bank account to any prisoner in {time_period}'
        ),
        total='credit_count',
        profile='sender_profile',
        limit=4,
        time_period=TIME_PERIOD.LAST_4_WEEKS
    ),
    'DRFREQ': TotalsRule(
        'DRFREQ',
        _(
            'More than {limit} disbursements from '
            'any prisoner to the same bank account in {time_period}'
        ),
        total='disbursement_count',
        profile='recipient_profile',
        limit=4,
        time_period=TIME_PERIOD.LAST_4_WEEKS
    ),
    'CSNUM': TotalsRule(
        'CSNUM',
        _(
            'A prisoner getting money from more than {limit} '
            'debit cards or bank accounts in {time_period}'
        ),
        total='sender_count',
        profile='prisoner_profile',
        limit=4,
        time_period=TIME_PERIOD.LAST_4_WEEKS
    ),
    'DRNUM': TotalsRule(
        'DRNUM',
        _(
            'A prisoner sending money to more than {limit} '
            'bank accounts in {time_period}'
        ),
        total='recipient_count',
        profile='prisoner_profile',
        limit=4,
        time_period=TIME_PERIOD.LAST_4_WEEKS
    ),
    'CPNUM': TotalsRule(
        'CPNUM',
        _(
            'A debit card or bank account sending money to more than '
            '{limit} prisoners in {time_period}'
        ),
        total='prisoner_count',
        profile='sender_profile',
        limit=4,
        time_period=TIME_PERIOD.LAST_4_WEEKS
    ),
    'DPNUM': TotalsRule(
        'DPNUM',
        _(
            'A bank account getting money from more than {limit} '
            'prisoners in {time_period}'
        ),
        total='prisoner_count',
        profile='recipient_profile',
        limit=4,
        time_period=TIME_PERIOD.LAST_4_WEEKS
    ),
}
