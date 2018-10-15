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
from .models import Event, EventCredit, EventDisbursement

INPUT_TYPES = Choices(
    ('NUMBER', 'number', _('Number')),
    ('STRING', 'string', _('String')),
)


class BaseRule():

    def __init__(self, model, description, inputs, static_inputs=[]):
        self.model = model
        self.description = description
        self.inputs = inputs
        self.static_inputs = static_inputs

    def create_events(self, subscription):
        raise NotImplementedError

    def get_query(self, subscription):
        provided_parameters = [
            ~Q(**{p.field: p.value}) if p.exclude
            else Q(**{p.field: p.value}) for p
            in subscription.parameters.all()
        ]
        static_parameters = [
            ~Q(**{i.field: i.default_value}) if i.exclude
            else Q(**{i.field: i.default_value}) for i
            in self.static_inputs
        ]
        return reduce(Q.__and__, provided_parameters + static_parameters)

    def get_max_event_ref_number(self, subscription):
        try:
            max_ref_number = Event.objects.filter(
                subscription__user=subscription.user
            ).latest('ref_number').ref_number
        except Event.DoesNotExist:
            max_ref_number = 0
        return max_ref_number


class Input():

    def __init__(
        self, field, input_type, choices=None, default_value=None,
        exclude=False
    ):
        self.field = field
        self.input_type = input_type
        self.choices = choices
        self.default_value = default_value
        self.exclude = exclude


class QueryRule(BaseRule):

    def get_query(self, subscription):
        query = super().get_query(subscription)
        if self.model in (Credit, Disbursement):
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
            events__subscription=subscription
        )

        max_ref_number = self.get_max_event_ref_number(subscription)
        for record in records:
            max_ref_number += 1
            event = Event.objects.create(
                subscription=subscription,
                ref_number=max_ref_number
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
        super().__init__(model, description, inputs, *args, **kwargs)

    def create_events(self, subscription):
        for rule in self.rules:
            rule.create_events(subscription)


class TimePeriodQuantityRule(BaseRule):

    def __init__(self, model, description, inputs, profile=None, *args, **kwargs):
        self.profile = profile
        super().__init__(model, description, inputs, *args, **kwargs)

    def get_query(self, subscription):
        query = super().get_query(subscription)
        if self.profile in (PrisonerProfile, SenderProfile, RecipientProfile):
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
                events__subscription=subscription
            )

            triggering_records = all_records.exclude(
                created__lt=subscription.start
            ).order_by('-created')[:1]

            if len(triggering_records):
                max_ref_number = self.get_max_event_ref_number(subscription) + 1
                event = Event.objects.create(
                    subscription=subscription,
                    ref_number=max_ref_number
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


amount_input = Input('amount__gte', INPUT_TYPES.NUMBER)
not_whole_amount_input = Input(
    'amount__endswith', INPUT_TYPES.NUMBER, default_value='00', exclude=True
)
time_period_input = Input(
    'totals__time_period', INPUT_TYPES.STRING, choices=TIME_PERIOD
)
sent_disbursements_only = Input(
    'resolution', INPUT_TYPES.STRING, default_value=DISBURSEMENT_RESOLUTION.SENT
)


RULES = {
    'NWN': CombinedRule(
        None,
        _('Credits or disbursements that are not a whole number'),
        [],
        rules=[
            QueryRule(Credit, None, [], static_inputs=[not_whole_amount_input]),
            QueryRule(Disbursement, None, [], static_inputs=[not_whole_amount_input, sent_disbursements_only])
        ]
    ),
    'CSFREQ': TimePeriodQuantityRule(
        Credit,
        _('More than {} credits from the same debit card or bank account to any prisoner within {}'),
        [
            time_period_input,
            Input('totals__credit_count__gte', INPUT_TYPES.NUMBER),
        ],
        profile=SenderProfile
    ),
    'DRFREQ': TimePeriodQuantityRule(
        Disbursement,
        _('More than {} disbursements from any prisoner to the same bank account within {}'),
        [
            time_period_input,
            Input('totals__disbursement_count__gte', INPUT_TYPES.NUMBER),
        ],
        profile=RecipientProfile
    ),
    'CSNUM': TimePeriodQuantityRule(
        Credit,
        _('A prisoner getting money from more than {} debit cards or bank accounts within {}'),
        [
            time_period_input,
            Input('totals__sender_count__gte', INPUT_TYPES.NUMBER),
        ],
        profile=PrisonerProfile
    ),
    'DRNUM': TimePeriodQuantityRule(
        Disbursement,
        _('A prisoner sending money to more than {} bank accounts within {}'),
        [
            time_period_input,
            Input('totals__recipient_count__gte', INPUT_TYPES.NUMBER),
        ],
        profile=PrisonerProfile
    ),
    'CPNUM': TimePeriodQuantityRule(
        Credit,
        _('A debit card of bank account sending money to more than {} prisoners within {}'),
        [
            time_period_input,
            Input('totals__prisoner_count__gte', INPUT_TYPES.NUMBER),
        ],
        profile=SenderProfile
    ),
    'DPNUM': TimePeriodQuantityRule(
        Disbursement,
        _('A bank account getting money from more than {} prisoners within {}'),
        [
            time_period_input,
            Input('totals__prisoner_count__gte', INPUT_TYPES.NUMBER),
        ],
        profile=RecipientProfile
    ),
    'VOX': CombinedRule(
        None,
        'Credits or disbursements over £{}',
        [amount_input],
        rules=[
            QueryRule(Credit, None, []),
            QueryRule(Disbursement, None, [], static_inputs=[sent_disbursements_only])
        ]
    ),
}
