from functools import reduce

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from extended_choices import Choices

from credit.models import Credit
from disbursement.constants import DISBURSEMENT_RESOLUTION
from disbursement.models import Disbursement
from mtp_auth.models import PrisonUserMapping
from security.constants import TIME_PERIOD, get_start_date_for_time_period
from security.models import PrisonerProfile, SenderProfile, RecipientProfile
from transaction.utils import format_amount
from .models import Event, EventCredit, EventDisbursement

INPUT_TYPES = Choices(
    ('NUMBER', 'number', _('Number')),
    ('STRING', 'string', _('String')),
    ('AMOUNT', 'amount', _('Amount')),
    ('OBJECT_ID', 'object_id', _('Object ID')),
    ('BOOLEAN', 'boolean', _('Boolean')),
)


class BaseRule:
    parent = None

    def __init__(self, code, model, description, inputs, limit_prisons=False):
        self.code = code
        self.model = model
        self.description = description
        self.inputs = inputs
        self.limit_prisons = limit_prisons

    def create_events(self, subscription=None):
        raise NotImplementedError

    def get_query(self, subscription=None):
        parameters = [
            ~Q(**{i.field: i.get_value(subscription)}) if i.exclude
            else Q(**{i.field: i.get_value(subscription)}) for i
            in self.inputs
        ]
        return reduce(Q.__and__, parameters)

    def get_event_description(self, subscription=None):
        if self.parent:
            return self.parent.get_event_description(subscription)
        input_values = {}
        for rule_input in self.inputs:
            input_values[rule_input.field] = (
                rule_input.get_display_value(subscription)
            )
        return self.description.format(**input_values)


class Input:

    def __init__(
        self, field, input_type, choices=None, default_value=None,
        exclude=False, editable=True
    ):
        self.field = field
        self.input_type = input_type
        self.choices = choices
        self.default_value = default_value
        self.exclude = exclude
        self.editable = editable

    def get_value(self, subscription=None):
        if subscription and self.editable:
            for parameter in subscription.parameters.all():
                if parameter.field == self.field:
                    return parameter.value
        return self.default_value

    def get_display_value(self, subscription=None):
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

    def get_value(self, subscription=None):
        return subscription.user if subscription else None


class QueryRule(BaseRule):

    def get_query(self, subscription=None):
        query = super().get_query(subscription)
        if subscription and self.limit_prisons and self.model in (Credit, Disbursement):
            prisons = PrisonUserMapping.objects.get_prison_set_for_user(
                subscription.user
            )
            if prisons.count():
                query = query & Q(prison__in=prisons)
        return query

    def create_events(self, subscription=None):
        records = self.model.objects.filter(
            self.get_query(subscription)
        ).exclude(
            events__rule=self.code
        )

        for record in records:
            event = Event.objects.create(
                rule=self.code,
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

    def __init__(self, code, model, description, inputs, rules=[], **kwargs):
        self.rules = rules
        for rule in self.rules:
            rule.parent = self
        super().__init__(code, model, description, inputs, **kwargs)

    def create_events(self, subscription=None):
        for rule in self.rules:
            rule.create_events(subscription)


class ProfileRule(BaseRule):

    def __init__(self, code, model, description, inputs, profile=None, **kwargs):
        self.profile = profile
        super().__init__(code, model, description, inputs, **kwargs)

    def get_query(self, subscription=None):
        query = super().get_query(subscription)
        if subscription and self.limit_prisons and self.profile in (
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

    def create_events(self, subscription=None):
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
                events__rule=self.code
            )

            if time_period_input in self.inputs:
                all_records = all_records.filter(
                    created__gte=get_start_date_for_time_period(
                        time_period_input.get_value(subscription)
                    )
                )

            triggering_records = all_records.order_by('-created')[:1]

            if len(triggering_records):
                event = Event.objects.create(
                    rule=self.code,
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
    'amount__endswith', INPUT_TYPES.STRING, default_value='00',
    exclude=True, editable=False
)
time_period_input = Input(
    'totals__time_period', INPUT_TYPES.STRING, choices=TIME_PERIOD,
    default_value=TIME_PERIOD.LAST_30_DAYS
)
sent_disbursements_only = Input(
    'resolution', INPUT_TYPES.STRING, default_value=DISBURSEMENT_RESOLUTION.SENT,
    editable=False
)


RULES = {
    'MON': CombinedRule(
        'MON',
        None,
        _('All transactions you’re monitoring — prisoners, debit cards, bank accounts'),
        [],
        rules=[
            ProfileRule(
                'MON',
                Credit,
                None,
                [Input(
                    'bank_transfer_details__sender_bank_account__monitoring_users__isnull',
                    INPUT_TYPES.BOOLEAN, default_value=False, editable=False
                )],
                profile=SenderProfile
            ),
            ProfileRule(
                'MON',
                Credit,
                None,
                [Input(
                    'debit_card_details__monitoring_users__isnull',
                    INPUT_TYPES.BOOLEAN, default_value=False, editable=False
                )],
                profile=SenderProfile
            ),
            ProfileRule(
                'MON',
                Credit,
                None,
                [Input(
                    'monitoring_users__isnull', INPUT_TYPES.BOOLEAN,
                    default_value=False, editable=False
                )],
                profile=PrisonerProfile
            ),
            ProfileRule(
                'MON',
                Disbursement,
                None,
                [Input(
                    'bank_transfer_details__recipient_bank_account__monitoring_users__isnull',
                    INPUT_TYPES.BOOLEAN, default_value=False, editable=False
                )],
                profile=RecipientProfile
            ),
            ProfileRule(
                'MON',
                Disbursement,
                None,
                [Input(
                    'monitoring_users__isnull', INPUT_TYPES.BOOLEAN,
                    default_value=False, editable=False
                )],
                profile=PrisonerProfile
            ),
        ]
    ),
    'NWN': CombinedRule(
        'NWN',
        None,
        _('Credits or disbursements that are not a whole number'),
        [],
        rules=[
            QueryRule('NWN', Credit, None, [not_whole_amount_input]),
            QueryRule('NWN', Disbursement, None, [not_whole_amount_input, sent_disbursements_only])
        ]
    ),
    'CSFREQ': ProfileRule(
        'CSFREQ',
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
        'DRFREQ',
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
        'CSNUM',
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
        'DRNUM',
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
        'CPNUM',
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
        'DPNUM',
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
        'VOX',
        None,
        'Credits or disbursements over £{amount__gte}',
        [amount_input],
        rules=[
            QueryRule('VOX', Credit, None, [amount_input]),
            QueryRule('VOX', Disbursement, None, [amount_input, sent_disbursements_only])
        ]
    ),
}
