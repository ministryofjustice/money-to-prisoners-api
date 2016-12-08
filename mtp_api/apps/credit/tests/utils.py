from itertools import cycle
from math import ceil
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
    if random.random() < 0.8:
        amount = random.randrange(500, 5000, 500)
    else:
        amount = random.randrange(500, 30000, 500)
    if random.random() < 0.1:
        amount += random.randint(0, 1000)
    return amount


def build_sender_prisoner_pairs(senders, prisoners):
    number_of_senders = len(senders)
    number_of_prisoners = len(prisoners)

    sender_prisoner_pairs = []
    for i in range(number_of_senders*3):
        prisoner_fraction = number_of_prisoners
        if i <= number_of_senders:
            sender_fraction = number_of_senders
            if i % 3 == 1:
                prisoner_fraction = ceil(number_of_prisoners/2)
            elif i % 3 == 2:
                prisoner_fraction = ceil(number_of_prisoners/15)
        elif i <= number_of_senders*2:
            sender_fraction = ceil(number_of_senders/2)
        else:
            sender_fraction = ceil(number_of_senders/15)

        sender_prisoner_pairs.append(
            (senders[i % sender_fraction], prisoners[i % prisoner_fraction])
        )
    return sender_prisoner_pairs
