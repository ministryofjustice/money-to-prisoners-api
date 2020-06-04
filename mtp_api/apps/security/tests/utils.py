from django.contrib.auth.models import Group

from credit.models import CREDIT_RESOLUTION, LOG_ACTIONS as CREDIT_LOG_ACTIONS
from payment.models import Payment, PAYMENT_STATUS
from payment.tests.utils import generate_payments
from security.models import Check, PrisonerProfile, SenderProfile


def generate_checks():
    checks = []
    fiu = Group.objects.get(name='FIU').user_set.first()
    for prisoner_profile in PrisonerProfile.objects.all():
        prisoner_profile.monitoring_users.add(fiu)

    candidate_payment = Payment.objects.filter(
        status=PAYMENT_STATUS.PENDING,
        credit__resolution=CREDIT_RESOLUTION.INITIAL,
        credit__owner__isnull=True,
        credit__sender_profile__isnull=True,
        credit__prisoner_profile__isnull=True,
    ).first()
    if not candidate_payment:
        candidate_payment = generate_payments(payment_batch=1, overrides={
            'status': PAYMENT_STATUS.PENDING,
            'owner': None,
            'prisoner_profile_id': None,
            'sender_profile_id': None
        })[0]

    credit = candidate_payment.credit

    credit.log_set.filter(action=CREDIT_LOG_ACTIONS.CREDITED).delete()
    checks.append(Check.objects.create_for_credit(credit))

    candidate_payment = Payment.objects.filter(
        status=PAYMENT_STATUS.PENDING,
        credit__resolution=CREDIT_RESOLUTION.INITIAL,
        credit__owner__isnull=True,
        credit__prisoner_number__isnull=False,
        credit__prisoner_name__isnull=False,
        credit__sender_profile__isnull=False
    ).first()
    if not candidate_payment:
        sender = SenderProfile.objects.filter(debit_card_details__isnull=False).order_by('-credit_count').first()
        candidate_payment = generate_payments(payment_batch=1, overrides={
            'status': PAYMENT_STATUS.PENDING,
            'owner': None,
            'credit': {
                'prisoner_number': 'A0990WX',
                'prisoner_name': 'JAMES SMITH',
                'sender_profile': sender
            }
        })[0]

    credit = candidate_payment.credit
    credit.log_set.filter(action=CREDIT_LOG_ACTIONS.CREDITED).delete()
    checks.append(Check.objects.create_for_credit(credit))

    return checks
