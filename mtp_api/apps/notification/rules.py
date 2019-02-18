from functools import reduce

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from extended_choices import Choices

from credit.models import Credit
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from mtp_auth.models import PrisonUserMapping
from security.constants import TIME_PERIOD
from security.models import PrisonerProfile, SenderProfile, RecipientProfile
from transaction.utils import format_amount
from .models import Event, EventCredit, EventDisbursement

INPUT_TYPES = Choices(
    ('NUMBER', 'number', _('Number')),
    ('STRING', 'string', _('String')),
    ('AMOUNT', 'amount', _('Amount')),
    ('OBJECT_ID', 'object_id', _('Object ID')),
)


class BaseRule:
    parent = None

    def __init__(self, model, description, inputs, limit_prisons=True):
        self.model = model
        self.description = description
        self.inputs = inputs
        self.limit_prisons = limit_prisons

    def create_events(self, subscription):
        raise NotImplementedError

    def get_query(self, subscription):
        parameters = [
            ~Q(**{i.field: i.get_value(subscription)}) if i.exclude
            else Q(**{i.field: i.get_value(subscription)}) for i
            in self.inputs
        ]
        return reduce(Q.__and__, parameters)

    def get_event_description(self, subscription):
        if self.parent:
            return self.parent.get_event_description(subscription)
        input_values = {}
        parameters = subscription.parameters.all()
        for rule_input in self.inputs:
            for parameter in parameters:
                if parameter.field == rule_input.field:
                    input_values[rule_input.field] = (
                        rule_input.get_display_value(parameter)
                    )
        return self.description.format(**input_values)


class Input:

    def __init__(
        self, field, input_type, choices=None, default_value=None,
        exclude=False, editable=False
    ):
        self.field = field
        self.input_type = input_type
        self.choices = choices
        self.default_value = default_value
        self.exclude = exclude
        self.editable = editable

    def get_value(self, subscription):
        if self.editable:
            for parameter in subscription.parameters.all():
                if parameter.field == self.field:
                    return parameter.value
        return self.default_value

    def get_display_value(self, subscription):
        value = self.get_value(subscription)
        if self.choices and isinstance(self.choices, Choices):
            try:
                value = self.choices.for_value(value).display
            except KeyError:
                pass
        elif self.input_type == INPUT_TYPES.AMOUNT:
            value = format_amount(int(value), trim_empty_pence=True, pound_sign=False)
        return value


class DefaultUserInput(Input):

    def get_value(self, subscription):
        return subscription.user


class QueryRule(BaseRule):

    def get_query(self, subscription):
        query = super().get_query(subscription)
        if self.limit_prisons and self.model in (Credit, Disbursement):
            prisons = PrisonUserMapping.objects.get_prison_set_for_user(
                subscription.user
            )
            if prisons.count():
                query = query & Q(prison__in=prisons)
        return query

    def create_events(self, subscription):
        records = self.model.objects.filter(
            self.get_query(subscription)
        ).exclude(
            created__lt=subscription.start
        ).exclude(
            events__rule=subscription.rule,
            events__user=subscription.user
        )

        for record in records:
            event = Event.objects.create(
                rule=subscription.rule,
                user=subscription.user,
                description=self.get_event_description(subscription)
            )

            if self.model == Credit:
                EventCredit.objects.create(
                    event=event,
                    credit=record,
                    triggering=True
                )
            elif self.model == Disbursement:
                EventDisbursement.objects.create(
                    event=event,
                    disbursement=record,
                    triggering=True
                )


class CombinedRule(BaseRule):

    def __init__(self, model, description, inputs, rules=[], *args, **kwargs):
        self.rules = rules
        for rule in self.rules:
            rule.parent = self
        super().__init__(model, description, inputs, *args, **kwargs)

    def create_events(self, subscription):
        for rule in self.rules:
            rule.create_events(subscription)


class ProfileRule(BaseRule):

    def __init__(self, model, description, inputs, profile=None, *args, **kwargs):
        self.profile = profile
        super().__init__(model, description, inputs, *args, **kwargs)

    def get_query(self, subscription):
        query = super().get_query(subscription)
        if self.limit_prisons and self.profile in (
            PrisonerProfile, SenderProfile, RecipientProfile
        ):
            prisons = PrisonUserMapping.objects.get_prison_set_for_user(
                subscription.user
            )
            if prisons.count():
                if self.profile == PrisonerProfile:
                    query = query & Q(current_prison__in=prisons)
                else:
                    query = query & Q(prisoners__current_prison__in=prisons)
        return query

    def create_events(self, subscription):
        profiles = self.profile.objects.filter(
            self.get_query(subscription)
        )

        for profile in profiles:
            if self.model == Credit:
                model_set = profile.credits
                relation_model = EventCredit
                related_field = 'credit'
            elif self.model == Disbursement:
                model_set = profile.disbursements
                relation_model = EventDisbursement
                related_field = 'disbursement'

            all_records = model_set.exclude(
                events__rule=subscription.rule,
                events__user=subscription.user
            )

            triggering_records = all_records.exclude(
                created__lt=subscription.start
            ).order_by('-created')[:1]

            if len(triggering_records):
                event = Event.objects.create(
                    rule=subscription.rule,
                    user=subscription.user,
                    description=self.get_event_description(subscription)
                )
                triggering_record = triggering_records[0]
                other_records = all_records.exclude(pk=triggering_record.pk)

                event_relations = [relation_model(
                    event=event,
                    triggering=True,
                    **{related_field: triggering_record},
                )]

                for record in other_records:
                    event_relations.append(relation_model(
                        event=event,
                        **{related_field: record},
                    ))

                relation_model.objects.bulk_create(event_relations)


amount_input = Input('amount__gte', INPUT_TYPES.AMOUNT, default_value=12000)
not_whole_amount_input = Input(
    'amount__endswith', INPUT_TYPES.STRING, default_value='00', exclude=True
)
time_period_input = Input(
    'totals__time_period', INPUT_TYPES.STRING, choices=TIME_PERIOD,
    default_value=TIME_PERIOD.LAST_30_DAYS
)
sent_disbursements_only = Input(
    'resolution', INPUT_TYPES.STRING, default_value=DISBURSEMENT_RESOLUTION.SENT
)


RULES = {
    'MON': CombinedRule(
        None,
        _('All transactions you’re monitoring — prisoners, debit cards, bank accounts'),
        [],
        rules=[
            ProfileRule(
                Credit,
                None,
                [DefaultUserInput(
                    'bank_transfer_details__sender_bank_account__monitoring_users',
                    INPUT_TYPES.OBJECT_ID
                )],
                profile=SenderProfile,
                limit_prisons=False
            ),
            ProfileRule(
                Credit,
                None,
                [DefaultUserInput(
                    'debit_card_details__monitoring_users', INPUT_TYPES.OBJECT_ID
                )],
                profile=SenderProfile,
                limit_prisons=False
            ),
            ProfileRule(
                Credit,
                None,
                [DefaultUserInput(
                    'monitoring_users', INPUT_TYPES.OBJECT_ID
                )],
                profile=PrisonerProfile,
                limit_prisons=False
            ),
            ProfileRule(
                Disbursement,
                None,
                [DefaultUserInput(
                    'bank_transfer_details__recipient_bank_account__monitoring_users',
                    INPUT_TYPES.OBJECT_ID
                )],
                profile=RecipientProfile,
                limit_prisons=False
            ),
            ProfileRule(
                Disbursement,
                None,
                [DefaultUserInput(
                    'monitoring_users', INPUT_TYPES.OBJECT_ID
                )],
                profile=PrisonerProfile,
                limit_prisons=False
            ),
        ]
    ),
    'NWN': CombinedRule(
        None,
        _('Credits or disbursements that are not a whole number'),
        [],
        rules=[
            QueryRule(Credit, None, [not_whole_amount_input]),
            QueryRule(Disbursement, None, [not_whole_amount_input, sent_disbursements_only])
        ]
    ),
    'CSFREQ': ProfileRule(
        Credit,
        _(
            'More than {totals__credit_count__gte} credits from the same debit '
            'card or bank account to any prisoner in {totals__time_period}'
        ),
        [
            time_period_input,
            Input('totals__credit_count__gte', INPUT_TYPES.NUMBER, default_value=5),
        ],
        profile=SenderProfile
    ),
    'DRFREQ': ProfileRule(
        Disbursement,
        _(
            'More than {totals__disbursement_count__gte} disbursements from '
            'any prisoner to the same bank account in {totals__time_period}'
        ),
        [
            time_period_input,
            Input('totals__disbursement_count__gte', INPUT_TYPES.NUMBER, default_value=5),
        ],
        profile=RecipientProfile
    ),
    'CSNUM': ProfileRule(
        Credit,
        _(
            'A prisoner getting money from more than {totals__sender_count__gte} '
            'debit cards or bank accounts in {totals__time_period}'
        ),
        [
            time_period_input,
            Input('totals__sender_count__gte', INPUT_TYPES.NUMBER, default_value=5),
        ],
        profile=PrisonerProfile
    ),
    'DRNUM': ProfileRule(
        Disbursement,
        _(
            'A prisoner sending money to more than {totals__recipient_count__gte} '
            'bank accounts in {totals__time_period}'
        ),
        [
            time_period_input,
            Input('totals__recipient_count__gte', INPUT_TYPES.NUMBER, default_value=5),
        ],
        profile=PrisonerProfile
    ),
    'CPNUM': ProfileRule(
        Credit,
        _(
            'A debit card or bank account sending money to more than '
            '{totals__prisoner_count__gte} prisoners in {totals__time_period}'
        ),
        [
            time_period_input,
            Input('totals__prisoner_count__gte', INPUT_TYPES.NUMBER, default_value=5),
        ],
        profile=SenderProfile
    ),
    'DPNUM': ProfileRule(
        Disbursement,
        _(
            'A bank account getting money from more than {totals__prisoner_count__gte} '
            'prisoners in {totals__time_period}'
        ),
        [
            time_period_input,
            Input('totals__prisoner_count__gte', INPUT_TYPES.NUMBER, default_value=5),
        ],
        profile=RecipientProfile
    ),
    'VOX': CombinedRule(
        None,
        'Credits or disbursements over £{amount__gte}',
        [amount_input],
        rules=[
            QueryRule(Credit, None, []),
            QueryRule(Disbursement, None, [sent_disbursements_only])
        ]
    ),
}
