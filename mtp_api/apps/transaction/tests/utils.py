import datetime
from itertools import cycle
import random
import warnings

from django.utils import timezone
from django.utils.crypto import get_random_string
from django.contrib.auth.models import User
from faker import Faker

from core.tests.utils import MockModelTimestamps
from prison.models import Prison, PrisonerLocation
from prison.tests.utils import random_prisoner_number, random_prisoner_dob, \
    random_prisoner_name, get_prisoner_location_creator, \
    load_nomis_prisoner_locations
from transaction.models import Transaction, Log
from transaction.constants import TRANSACTION_STATUS, LOG_ACTIONS

fake = Faker(locale='en_GB')


def random_sender_name():
    return fake.name()


def random_reference(prisoner_number=None, prisoner_dob=None):
    if not prisoner_number or not prisoner_dob:
        return get_random_string(length=15)
    return '%s %s' % (
        prisoner_number.upper(),
        prisoner_dob.strftime('%d/%m/%Y'),
    )


def generate_initial_transactions_data(tot=50, prisoner_location_generator=None):
    data_list = []

    now = timezone.now().replace(microsecond=0)

    for transaction_counter in range(1, tot + 1):
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

        random_date = now - datetime.timedelta(
            minutes=random.randint(0, 10000)
        )

        data = {
            'amount': random.randint(1000, 30000),
            'received_at': random_date,
            'sender_sort_code': get_random_string(6, '1234567890'),
            'sender_account_number': get_random_string(8, '1234567890'),
            'sender_name': random_sender_name(),
            'owner': None,
            'credited': False,
            'refunded': False,
            'created': random_date,
            'modified': random_date,
        }

        if include_prisoner_info:
            if prisoner_location_generator:
                data.update(next(prisoner_location_generator))
            else:
                data.update({
                    'prisoner_name': random_prisoner_name(),
                    'prisoner_number': random_prisoner_number(),
                    'prisoner_dob': random_prisoner_dob(),
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


def generate_predetermined_transactions_data():
    """
    Uses test NOMIS prisoner locations to create some transactions
    that are pre-determined for user testing with specific scenarios

    Currently, only one transaction is created:
        NICHOLAS FINNEY (A1450AE, dob. 30/12/1986) @ HMP BIRMINGHAM
        Mary Stevenson sent £72.30, 8 days ago
        Payment is still uncredited
    """
    prisoner_number = 'A1450AE'
    try:
        prisoner_location = PrisonerLocation.objects.get(
            prisoner_number=prisoner_number
        )
    except PrisonerLocation.DoesNotExist:
        warnings.warn('Could not find prisoner %s, '
                      'was test NOMIS data loaded?' % prisoner_number)
        return []

    now = timezone.now().replace(microsecond=0)
    over_a_week_ago = now - datetime.timedelta(days=8)
    data = {
        'received_at': over_a_week_ago,
        'created': over_a_week_ago,
        'modified': over_a_week_ago,
        'owner': None,
        'credited': False,
        'refunded': False,

        'sender_name': 'Mary Stevenson',
        'amount': 7230,
        'sender_sort_code': '680966',
        'sender_account_number': '75823963',

        'prison': prisoner_location.prison,
        'prisoner_name': prisoner_location.prisoner_name,
        'prisoner_number': prisoner_location.prisoner_number,
        'prisoner_dob': prisoner_location.prisoner_dob,
    }
    data['reference'] = random_reference(
        data.get('prisoner_number'), data.get('prisoner_dob')
    )
    data_list = [data]
    return data_list


def get_owner_and_status_chooser():
    clerks_per_prison = {}
    for p in Prison.objects.all():
        user_ids = p.prisonusermapping_set.values_list('user', flat=True)
        clerks_per_prison[p.pk] = (
            cycle(list(User.objects.filter(id__in=user_ids))),
            cycle([
                TRANSACTION_STATUS.LOCKED,
                TRANSACTION_STATUS.AVAILABLE,
                TRANSACTION_STATUS.CREDITED
            ])
        )

    def internal_function(prison):
        user, status = clerks_per_prison[prison.pk]
        return next(user), next(status)

    return internal_function


def generate_transactions(
    transaction_batch=50,
    use_test_nomis_prisoners=False,
    predetermined_transactions=False,
    only_new_transactions=False,
):
    if use_test_nomis_prisoners:
        prisoner_location_generator = cycle(load_nomis_prisoner_locations())
    else:
        prisoner_location_generator = None
    data_list = generate_initial_transactions_data(
        tot=transaction_batch,
        prisoner_location_generator=prisoner_location_generator,
    )

    location_creator = get_prisoner_location_creator()
    if only_new_transactions:
        def owner_status_chooser(*args):
            return None, TRANSACTION_STATUS.AVAILABLE
    else:
        owner_status_chooser = get_owner_and_status_chooser()

    transactions = []
    for transaction_counter, data in enumerate(data_list, start=1):
        is_valid, prisoner_location = location_creator(
            data.get('prisoner_name'), data.get('prisoner_number'),
            data.get('prisoner_dob'), data.get('prison'),
        )

        if is_valid:
            # randomly choose the state of the transaction
            prison = prisoner_location.prison
            owner, status = owner_status_chooser(prison)

            data['prison'] = prison
            if status == TRANSACTION_STATUS.LOCKED:
                data.update({
                    'owner': owner,
                    'credited': False
                })
            elif status == TRANSACTION_STATUS.AVAILABLE:
                data.update({
                    'owner': None,
                    'credited': False
                })
            elif status == TRANSACTION_STATUS.CREDITED:
                data.update({
                    'owner': owner,
                    'credited': True
                })
        else:
            if transaction_counter % 2 == 0:
                data.update({'refunded': True})
            else:
                data.update({'refunded': False})

        with MockModelTimestamps(data['created'], data['modified']):
            new_transaction = Transaction.objects.create(**data)
        transactions.append(new_transaction)

    if predetermined_transactions:
        for data in generate_predetermined_transactions_data():
            with MockModelTimestamps(data['created'], data['modified']):
                new_transaction = Transaction.objects.create(**data)
            transactions.append(new_transaction)

    for new_transaction in transactions:
        with MockModelTimestamps(new_transaction.created, new_transaction.modified):
            log_data = {
                'transaction': new_transaction,
                'user': new_transaction.owner,
            }

            if new_transaction.credited:
                log_data['action'] = LOG_ACTIONS.CREDITED
                Log.objects.create(**log_data)
            elif new_transaction.refunded:
                log_data['action'] = LOG_ACTIONS.REFUNDED
                Log.objects.create(**log_data)

    return transactions
