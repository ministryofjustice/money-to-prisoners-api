import random

import faker
from django.contrib.auth.models import Group

from credit.models import Credit, CREDIT_RESOLUTION, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from prison.models import Prison
from payment.models import Payment, PAYMENT_STATUS
from payment.tests.utils import generate_payments
from security.models import Check, PrisonerProfile, SenderProfile
from django.db.models import Count

fake = faker.Faker()

PAYMENT_FILTERS_FOR_INVALID_CHECK = dict(
    status=PAYMENT_STATUS.PENDING,
    credit=dict(
        resolution=CREDIT_RESOLUTION.INITIAL,
        owner_id=None,
        sender_profile_id=None,
        prisoner_profile_id=None,
        prison_id__isnull=False
    )
)

PAYMENT_FILTERS_FOR_VALID_CHECK = dict(
    status=PAYMENT_STATUS.PENDING,
    credit=dict(
        resolution=CREDIT_RESOLUTION.INITIAL,
        # This only works because get_or_create ignores values with __ in any call to create()
        # these values must be included in the defaults if NOT NULL
        owner__isnull=True,
        prisoner_number__isnull=False,
        prisoner_name__isnull=False,
        sender_profile__isnull=False,
        prison_id__isnull=False
    )
)


def _get_credit_values(credit_filters):
    return dict(
        {
            'amount': random.randint(100, 1000000),
            'prisoner_number': random.randint(100, 1000000),
            'prisoner_name': fake.name(),
            'prisoner_profile_id': random.choice(
                PrisonerProfile.objects.annotate(
                    cred_count=Count('credits')
                ).order_by('-cred_count').all()[:5]
            ).id,
            'sender_profile_id': random.choice(
                SenderProfile.objects.filter(
                    debit_card_details__isnull=False
                ).annotate(
                    cred_count=Count('credits')
                ).order_by('-cred_count').all()[:5]
            ).id,
            'prison_id': random.choice(Prison.objects.all()).nomis_id
        },
        **{
            key: val for key, val in credit_filters.items()
            if '__' not in key
        }
    )


def generate_checks(number_of_checks=1, specific_payments_to_check=tuple()):
    checks = []
    fiu = Group.objects.get(name='FIU').user_set.first()
    for prisoner_profile in PrisonerProfile.objects.all():
        prisoner_profile.monitoring_users.add(fiu)
        prisoner_profile.save()
    for sender_profile in SenderProfile.objects.all():
        monitored_instance = None
        if sender_profile.debit_card_details.count():
            monitored_instance = sender_profile.debit_card_details.first()
        elif sender_profile.bank_transfer_details.count():
            monitored_instance = sender_profile.bank_transfer_details.first().sender_bank_account
        if monitored_instance:
            monitored_instance.monitoring_users.add(fiu)
            monitored_instance.save()

    filters = [
        PAYMENT_FILTERS_FOR_INVALID_CHECK,
        *([PAYMENT_FILTERS_FOR_VALID_CHECK] * number_of_checks),
        *specific_payments_to_check
    ]
    for filter_set in filters:
        credit_filters = filter_set.pop('credit', {})
        candidate_payment = Payment.objects.filter(
            credit=Credit.objects.filter(
                **credit_filters
            ).get_or_create(**_get_credit_values(credit_filters))[0],
            **filter_set
        ).first()
        if not candidate_payment:
            candidate_payment = generate_payments(payment_batch=1, overrides=dict(
                credit=_get_credit_values(credit_filters),
                **filter_set
            ))[0]
        candidate_payment.credit.log_set.filter(action=CREDIT_LOG_ACTIONS.CREDITED).delete()
        checks.append(Check.objects.create_for_credit(candidate_payment.credit))

    return checks
