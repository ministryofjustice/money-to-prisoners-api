from django.contrib.auth.models import Group

from credit.models import Credit, CREDIT_RESOLUTION, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from payment.models import Payment, PAYMENT_STATUS
from payment.tests.utils import generate_payments
from security.models import Check, PrisonerProfile, SenderProfile


def _get_credit_values(credit_filters):
    return dict(
        {
            'amount': 10000,
            'prisoner_number': 24601,
            'prisoner_name': 'Jean ValJean',
            'sender_profile': SenderProfile.objects.filter(
                debit_card_details__isnull=False
            ).order_by('-credit_count').first()
        },
        **credit_filters
    )


def generate_checks(specific_payments_to_check=tuple()):
    checks = []
    fiu = Group.objects.get(name='FIU').user_set.first()
    for prisoner_profile in PrisonerProfile.objects.all():
        prisoner_profile.monitoring_users.add(fiu)

    filters = [
        dict(
            status=PAYMENT_STATUS.PENDING,
            credit=dict(
                resolution=CREDIT_RESOLUTION.INITIAL,
                owner_id=None,
                sender_profile_id=None,
                prisoner_profile_id=None,
            )
        ),
        dict(
            status=PAYMENT_STATUS.PENDING,
            credit=dict(
                resolution=CREDIT_RESOLUTION.INITIAL,
                # This only works because get_or_create ignores values with __ in any call to create()
                # these values must be included in the defaults if NOT NULL
                owner__isnull=True,
                prisoner_number__isnull=False,
                prisoner_name__isnull=False,
                sender_profile__isnull=False
            )
        ),
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
            candidate_payment = generate_payments(payment_batch=1, overrides={
                **filter_set
            })[0]
        candidate_payment.credit.log_set.filter(action=CREDIT_LOG_ACTIONS.CREDITED).delete()
        checks.append(Check.objects.create_for_credit(candidate_payment.credit))

    return checks
