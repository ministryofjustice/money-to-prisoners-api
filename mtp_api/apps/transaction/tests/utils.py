import datetime
import random
from itertools import cycle

from django.utils import timezone
from django.utils.crypto import get_random_string
from django.contrib.auth.models import User

from prison.models import Prison

from transaction.models import Transaction
from transaction.constants import TRANSACTION_STATUS

from prison.tests.utils import random_prisoner_number, random_prisoner_dob, \
    get_prisoner_location_creator


def random_reference(prisoner_number=None, prisoner_dob=None):
    if not prisoner_number or not prisoner_dob:
        return get_random_string(length=15)
    return '%s %s' % (
        prisoner_number.lower(),
        prisoner_dob.strftime('%d%b%Y').lower()
    )


def generate_initial_transactions_data(tot=50):
    data_list = []

    now = timezone.now().replace(microsecond=0)

    for transaction_counter in range(1, tot+1):
        # Records might not have prisoner data and/or might not
        # have building society roll numbers.
        # Atm, we set the probability of it having prisoner info
        # to 80% which is an arbitrary high value as we expect
        # records to have correct data most of the time.
        # The probability of transactions coming from building
        # societies is instead low, set here to 10%,
        # which is again arbitrary.
        include_prisoner_info = transaction_counter % 5 != 0
        include_sender_roll_number = transaction_counter % 10 == 0

        data = {
            'amount': random.randint(1000, 30000),
            'received_at': now - datetime.timedelta(
                minutes=random.randint(0, 10000)
            ),
            'sender_sort_code': get_random_string(6, '1234567890'),
            'sender_account_number': get_random_string(8, '1234567890'),
            'sender_name': get_random_string(10),
            'owner': None,
            'credited': False,
            'refunded': False
        }

        if include_prisoner_info:
            data.update({
                'prisoner_number': random_prisoner_number(),
                'prisoner_dob': random_prisoner_dob()
            })

        if include_sender_roll_number:
            data.update({
                'sender_roll_number': get_random_string(15, '1234567890')
            })

        data['reference'] = random_reference(
            data.get('prisoner_number'), data.get('prisoner_dob')
        )
        data_list.append(data)
    return data_list


def generate_transactions(transaction_batch=50):
    def get_owner_and_status_chooser():
        clerks_per_prison = {}
        for prison in Prison.objects.all():
            user_ids = prison.prisonusermapping_set.values_list('user', flat=True)
            clerks_per_prison[prison.pk] = (
                cycle(list(User.objects.filter(id__in=user_ids))),
                cycle([
                    TRANSACTION_STATUS.LOCKED,
                    TRANSACTION_STATUS.AVAILABLE,
                    TRANSACTION_STATUS.CREDITED
                ])
            )

        def internal_function(prison):
            user, status = clerks_per_prison[prison.pk]
            return (next(user), next(status))
        return internal_function

    data_list = generate_initial_transactions_data(
        tot=transaction_batch
    )

    location_creator = get_prisoner_location_creator()
    onwer_status_chooser = get_owner_and_status_chooser()

    transactions = []
    for transaction_counter, data in enumerate(data_list, start=1):
        is_valid, prisoner_location = location_creator(
            data.get('prisoner_number'), data.get('prisoner_dob')
        )
        if is_valid:
            # randomly choose the state of the transaction
            prison = prisoner_location.prison
            owner, t_status = onwer_status_chooser(prison)

            data['prison'] = prison
            if t_status == TRANSACTION_STATUS.LOCKED:
                data.update({
                    'owner': owner,
                    'credited': False
                })
            elif t_status == TRANSACTION_STATUS.AVAILABLE:
                data.update({
                    'owner': None,
                    'credited': False
                })
            elif t_status == TRANSACTION_STATUS.CREDITED:
                data.update({
                    'owner': owner,
                    'credited': True
                })
        else:
            if transaction_counter % 2 == 0:
                data.update({'refunded': True})
            else:
                data.update({'refunded': False})

        transactions.append(
            Transaction.objects.create(**data)
        )

    return transactions
