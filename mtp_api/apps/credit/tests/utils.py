from itertools import cycle
import random

from django.contrib.auth import get_user_model

from core.tests.utils import MockModelTimestamps
from credit.constants import CREDIT_STATUS, LOG_ACTIONS
from credit.models import Log
from prison.models import Prison

User = get_user_model()


def get_owner_and_status_chooser():
    clerks_per_prison = {}
    for p in Prison.objects.all():
        user_ids = p.prisonusermapping_set.filter(
            user__is_staff=False, user__groups__name='PrisonClerk'
        ).values_list('user', flat=True)
        clerks_per_prison[p.pk] = (
            cycle(list(User.objects.filter(id__in=user_ids))),
            cycle([
                CREDIT_STATUS.LOCKED,
                CREDIT_STATUS.AVAILABLE,
                CREDIT_STATUS.CREDITED
            ])
        )

    def internal_function(prison):
        user, status = clerks_per_prison[prison.pk]
        return next(user), next(status)

    return internal_function


def create_credit_log(credit, created, modified):
    with MockModelTimestamps(modified, modified):
        log_data = {
            'credit': credit,
            'user': credit.owner,
        }

        if credit.credited:
            log_data['action'] = LOG_ACTIONS.CREDITED
            Log.objects.create(**log_data)
        elif credit.refunded:
            log_data['action'] = LOG_ACTIONS.REFUNDED
            Log.objects.create(**log_data)
        elif credit.locked:
            log_data['action'] = LOG_ACTIONS.LOCKED
            Log.objects.create(**log_data)


def random_amount():
    amount = random.randrange(500, 30000, 500)
    if random.random() < 0.1:
        amount += random.randint(0, 1000)
    return amount
