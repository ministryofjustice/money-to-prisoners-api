import datetime
import unicodedata

from django.db.transaction import atomic
from django.utils import timezone
from django.utils.functional import cached_property

from core import getattr_path
from credit.models import Credit
from disbursement.models import Disbursement
from notification.models import (
    Event, CreditEvent, DisbursementEvent,
    SenderProfileEvent, RecipientProfileEvent, PrisonerProfileEvent,
)
from security.models import SenderProfile, RecipientProfile, PrisonerProfile, CheckAutoAcceptRule
from transaction.utils import format_amount

ENABLED_RULE_CODES = {'MONP', 'MONS'}


class Triggered:
    """
    'Truthy' type to indicate whether a notification rule is triggered by a record
    allowing the rule to add additional attributes to describe the trigger
    """

    def __init__(self, triggered, **kwargs):
        self.triggered = bool(triggered)
        self.kwargs = kwargs

    def __bool__(self):
        return self.triggered


class BaseRule:
    applies_to_models = (Credit, Disbursement)

    def __init__(self, code, description, abbr_description, applies_to_models=None, **kwargs):
        self.code = code
        self.description = description
        self.abbr_description = abbr_description
        self.kwargs = kwargs
        if applies_to_models:
            self.applies_to_models = applies_to_models

    def applies_to(self, record) -> bool:
        return isinstance(record, self.applies_to_models)

    def rule_specific_trigger(self, record) -> Triggered:
        raise NotImplementedError

    def triggered(self, record):
        """
        Determines whether a rule is triggered by the properties of the data object passed in

        For credits we first check auto-accept rules here, and if any apply and are active we do not trigger
        """
        if isinstance(record, Credit) and CheckAutoAcceptRule.objects.is_active_auto_accept_for_credit(record):
            return Triggered(False, active_auto_accept_rule=True)
        else:
            return self.rule_specific_trigger(record)

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
    def rule_specific_trigger(self, record) -> Triggered:
        return Triggered(record.amount % 100, amount=record.amount)


class HighAmountRule(BaseRule):
    def __init__(self, *args, limit, **kwargs):
        kwargs['limit'] = limit
        super().__init__(*args, **kwargs)
        self.description = self.description.format(
            display_limit=format_amount(limit, trim_empty_pence=True, pound_sign=True)
        )

    def rule_specific_trigger(self, record) -> Triggered:
        return Triggered(record.amount >= self.kwargs['limit'], amount=record.amount)


class ContainsSymbols(BaseRule):
    CATEGORIES = {
        'Sc', 'Sk', 'Sm', 'So',
        'Cn', 'Co', 'Cs',
    }

    def __init__(self, *args, record_attr_path, **kwargs):
        super().__init__(*args, **kwargs)
        self.record_attr_path = record_attr_path

    def rule_specific_trigger(self, record) -> Triggered:
        value = getattr_path(record, self.record_attr_path, None)
        if not value:
            contains_symbols = False
        else:
            contains_symbols = self.contains_symbols(value)
        return Triggered(contains_symbols)

    def contains_symbols(self, text):
        for char in text:
            category = unicodedata.category(char)
            if category in self.CATEGORIES:
                return True
        return False


class MonitoredRule(BaseRule):
    def __init__(self, *args, user_filters=None, **kwargs):
        kwargs['user_filters'] = user_filters or {}
        super().__init__(*args, **kwargs)

    @atomic
    def create_events(self, record):
        profile = self.get_event_trigger(record)
        user_filters = self.kwargs['user_filters']
        return [
            self._create_event(record, user=user)
            for user in profile.get_monitoring_users().filter(**user_filters)
        ]

    def rule_specific_trigger(self, record) -> Triggered:
        profile = self.get_event_trigger(record)
        if profile:
            user_filters = self.kwargs['user_filters']
            monitoring_user_count = profile.get_monitoring_users().filter(**user_filters).count()
            return Triggered(monitoring_user_count, monitoring_user_count=monitoring_user_count)
        return Triggered(False, monitoring_user_count=0)

    def get_event_trigger(self, record):
        return getattr(record, self.kwargs['profile'])


class CountingRule(BaseRule):
    def __init__(self, *args, profile, count, limit, days, **kwargs):
        """
        Counts a field (`count`) on records of the same type on related `profile` over the past n days.
        If count exceeds `limit`, rule is triggered.
        """
        super().__init__(*args, profile=profile, count=count, limit=limit, days=days, **kwargs)
        self.description = self.description.format(limit=limit)

    @cached_property
    def shared_profile(self):
        # these are catch-all profiles for records that cannot have their own unique ones
        # so counting rules would not be interesting or would need different limits
        # c.f. `update_security_profiles` command
        if self.kwargs['profile'] == 'sender_profile':
            try:
                return SenderProfile.objects.get_anonymous_sender()
            except SenderProfile.DoesNotExist:
                pass
        elif self.kwargs['profile'] == 'recipient_profile':
            try:
                return RecipientProfile.objects.get_cheque_recipient()
            except RecipientProfile.DoesNotExist:
                pass
        return None

    def rule_specific_trigger(self, record) -> Triggered:
        profile = self.get_event_trigger(record)
        if not profile or profile == self.shared_profile:
            return Triggered(False)

        records_of_same_type = self.get_profile_records_of_same_type(profile, record)
        field_to_count = self.kwargs['count']
        count = records_of_same_type.values(field_to_count).distinct().count()
        return Triggered(count > self.kwargs['limit'], count=count)

    def get_event_trigger(self, record):
        return getattr(record, self.kwargs['profile'])

    def get_profile_records_of_same_type(self, profile, record):
        if isinstance(record, Credit):
            period_end = record.received_at
        elif isinstance(record, Disbursement):
            period_end = record.created
        else:
            raise ValueError('unknown record')
        # make 4 week period include whole days at the boundaries in local time
        period_end = timezone.localtime(period_end) + datetime.timedelta(days=1)
        period_end = period_end.replace(hour=0, minute=0, second=0, microsecond=0)
        period_start = period_end - datetime.timedelta(days=self.kwargs['days'])

        if isinstance(record, Credit):
            return profile.credits.filter(received_at__gte=period_start, received_at__lt=period_end)
        if isinstance(record, Disbursement):
            return profile.disbursements.filter(created__gte=period_start, created__lt=period_end)


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
    'FIUMONP': MonitoredRule(
        'FIUMONP',
        description='Credits or disbursements for FIU prisoners',
        abbr_description='fiu prisoners',
        profile='prisoner_profile',
        user_filters={'groups__name': 'FIU'},
    ),
    'FIUMONS': MonitoredRule(
        'FIUMONS',
        description='Credits for FIU payment sources',
        abbr_description='fiu sources',
        applies_to_models=(Credit,),
        profile='sender_profile',
        user_filters={'groups__name': 'FIU'},
    ),
    'FIUMONR': MonitoredRule(
        'FIUMONR',
        description='Disbursements for FIU recipients',
        abbr_description='fiu recipients',
        applies_to_models=(Disbursement,),
        profile='recipient_profile',
        user_filters={'groups__name': 'FIU'},
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
    'CSYM': ContainsSymbols(
        'CSYM',
        description='Credits from debit cards or bank accounts with symbols in their name',
        abbr_description='symbols',
        applies_to_models=(Credit,),
        record_attr_path='sender_name',
    ),
    'CSFREQ': CountingRule(
        'CSFREQ',
        description='More than {limit} credits from the same debit card or bank account to any prisoner in a week',
        abbr_description='freq. source',
        applies_to_models=(Credit,),
        profile='sender_profile',
        count='pk',
        limit=3,
        days=8,
    ),
    'DRFREQ': CountingRule(
        'DRFREQ',
        description='More than {limit} disbursements from any prisoner to the same bank account in 4 weeks',
        abbr_description='freq. recipient',
        applies_to_models=(Disbursement,),
        profile='recipient_profile',
        count='pk',
        limit=4,
        days=29,
    ),
    'CSNUM': CountingRule(
        'CSNUM',
        description='A prisoner getting money from more than {limit} debit cards or bank accounts in a week',
        abbr_description='many senders',
        applies_to_models=(Credit,),
        profile='prisoner_profile',
        count='sender_profile',
        limit=3,
        days=8,
    ),
    'DRNUM': CountingRule(
        'DRNUM',
        description='A prisoner sending money to more than {limit} bank accounts in 4 weeks',
        abbr_description='many recipients',
        applies_to_models=(Disbursement,),
        profile='prisoner_profile',
        count='recipient_profile',
        limit=4,
        days=29,
    ),
    'CPNUM': CountingRule(
        'CPNUM',
        description='A debit card or bank account sending money to more than {limit} prisoners in a week',
        abbr_description='many prisoners',
        applies_to_models=(Credit,),
        profile='sender_profile',
        count='prisoner_profile',
        limit=3,
        days=8,
    ),
    'DPNUM': CountingRule(
        'DPNUM',
        description='A bank account getting money from more than {limit} prisoners in 4 weeks',
        abbr_description='many prisoners',
        applies_to_models=(Disbursement,),
        profile='recipient_profile',
        count='prisoner_profile',
        limit=4,
        days=29,
    ),
}
