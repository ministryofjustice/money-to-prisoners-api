import datetime
from functools import partial
from itertools import cycle
import random
import warnings

from django.utils import timezone
from django.utils.crypto import get_random_string
from django.contrib.auth.models import User
from faker import Faker

from core.tests.utils import MockModelTimestamps
from payment.models import Payment
from payment.constants import PAYMENT_STATUS
from prison.models import Prison, PrisonerLocation
from prison.tests.utils import random_prisoner_number, random_prisoner_dob, \
    random_prisoner_name, get_prisoner_location_creator, \
    load_nomis_prisoner_locations
from transaction.models import Transaction, Log
from transaction.constants import (
    TRANSACTION_STATUS, LOG_ACTIONS, TRANSACTION_CATEGORY, TRANSACTION_SOURCE
)

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


def latest_transaction_date():
    latest_transaction_date = timezone.now().replace(microsecond=0) - datetime.timedelta(days=1)
    while latest_transaction_date.weekday() > 4:
        latest_transaction_date = latest_transaction_date - datetime.timedelta(days=1)
    return latest_transaction_date


def generate_initial_transactions_data(
        tot=50,
        prisoner_location_generator=None,
        include_debits=True,
        include_administrative_credits=True,
        include_online_payments=True):
    data_list = []

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
        include_sender_roll_number = transaction_counter % 29 == 0
        make_debit_transaction = (
            include_debits and (transaction_counter + 1) % 5 == 0
        )
        make_administrative_credit_transaction = (
            include_administrative_credits and transaction_counter % 17 == 0
        )
        make_online_payment = (
            include_online_payments and transaction_counter % 13 == 0
        )

        random_date = latest_transaction_date() - datetime.timedelta(
            minutes=random.randint(0, 10000)
        )
        midnight_random_date = random_date.replace(hour=0, minute=0, second=0)
        data = {
            'category': TRANSACTION_CATEGORY.CREDIT,
            'amount': random.randint(1000, 30000),
            'received_at': midnight_random_date,
            'sender_sort_code': get_random_string(6, '1234567890'),
            'sender_account_number': get_random_string(8, '1234567890'),
            'sender_name': random_sender_name(),
            'owner': None,
            'credited': False,
            'refunded': False,
            'created': random_date,
            'modified': random_date,
        }

        if make_online_payment:
            data['source'] = TRANSACTION_SOURCE.ONLINE
            del data['sender_sort_code']
            del data['sender_account_number']

            if prisoner_location_generator:
                data.update(next(prisoner_location_generator))
            else:
                data.update({
                    'prisoner_name': random_prisoner_name(),
                    'prisoner_number': random_prisoner_number(),
                    'prisoner_dob': random_prisoner_dob(),
                })
        elif make_administrative_credit_transaction:
            data['source'] = TRANSACTION_SOURCE.ADMINISTRATIVE
            data['incomplete_sender_info'] = True
            del data['sender_sort_code']
            del data['sender_account_number']
        elif make_debit_transaction:
            data['source'] = TRANSACTION_SOURCE.ADMINISTRATIVE
            data['category'] = TRANSACTION_CATEGORY.DEBIT
            data['reference'] = 'Payment refunded'
        else:
            data['source'] = TRANSACTION_SOURCE.BANK_TRANSFER

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
    a_week_ago = over_a_week_ago + datetime.timedelta(days=1)
    data = {
        'received_at': over_a_week_ago.replace(hour=0, minute=0, second=0),
        'created': over_a_week_ago,
        'modified': a_week_ago,
        'owner': None,
        'credited': True,
        'refunded': False,

        'sender_name': 'Mary Stevenson',
        'amount': 7230,
        'category': TRANSACTION_CATEGORY.CREDIT,
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
    consistent_history=False,
    include_debits=True,
    include_administrative_credits=True,
    include_online_payments=True
):
    if use_test_nomis_prisoners:
        prisoner_location_generator = cycle(load_nomis_prisoner_locations())
    else:
        prisoner_location_generator = None
    data_list = generate_initial_transactions_data(
        tot=transaction_batch,
        prisoner_location_generator=prisoner_location_generator,
        include_debits=include_debits,
        include_administrative_credits=include_administrative_credits,
        include_online_payments=include_online_payments
    )

    location_creator = get_prisoner_location_creator()
    if only_new_transactions:
        def owner_status_chooser(*args):
            return None, TRANSACTION_STATUS.AVAILABLE
    else:
        owner_status_chooser = get_owner_and_status_chooser()

    transactions = []
    if consistent_history:
        create_transaction = partial(
            setup_historical_transaction,
            location_creator,
            owner_status_chooser,
            latest_transaction_date()
        )
    else:
        create_transaction = partial(
            setup_transaction,
            location_creator,
            owner_status_chooser
        )
    for transaction_counter, data in enumerate(data_list, start=1):
        new_transaction = create_transaction(transaction_counter, data)
        transactions.append(new_transaction)

    if predetermined_transactions:
        for data in generate_predetermined_transactions_data():
            with MockModelTimestamps(data['created'], data['modified']):
                new_transaction = Transaction.objects.create(**data)
                new_transaction.populate_ref_code()
            transactions.append(new_transaction)

    generate_transaction_logs(transactions)

    return transactions


def setup_historical_transaction(location_creator, owner_status_chooser,
                                 end_date, transaction_counter, data):
    if (data['category'] == TRANSACTION_CATEGORY.CREDIT and
            data['source'] == TRANSACTION_SOURCE.BANK_TRANSFER):
        is_valid, prisoner_location = location_creator(
            data.get('prisoner_name'), data.get('prisoner_number'),
            data.get('prisoner_dob'), data.get('prison'),
        )

        is_most_recent = data['received_at'].date() == end_date.date()
        if is_valid:
            prison = prisoner_location.prison
            owner, status = owner_status_chooser(prison)
            data['prison'] = prison
            if is_most_recent:
                data.update({
                    'owner': None,
                    'credited': False
                })
            else:
                data.update({
                    'owner': owner,
                    'credited': True
                })
        else:
            if is_most_recent:
                data.update({'refunded': False})
            else:
                data.update({'refunded': True})

    with MockModelTimestamps(data['created'], data['modified']):
        new_transaction = Transaction.objects.create(**data)
        new_transaction.populate_ref_code()

    return new_transaction


def setup_transaction(location_creator, owner_status_chooser,
                      transaction_counter, data):
    if data['category'] == TRANSACTION_CATEGORY.CREDIT:
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
        new_transaction.populate_ref_code()

    if data['source'] == TRANSACTION_SOURCE.ONLINE:
        payment = Payment()
        payment.transaction = new_transaction
        payment.status = PAYMENT_STATUS.TAKEN
        payment.amount = new_transaction.amount
        payment.prisoner_number = new_transaction.prisoner_number
        payment.prisoner_dob = new_transaction.prisoner_dob
        payment.processor_id = random.randint(100, 1000)
        payment.recipient_name = new_transaction.prisoner_name
        payment.save()

    return new_transaction


def generate_transaction_logs(transactions):
    for new_transaction in transactions:
        with MockModelTimestamps(new_transaction.modified, new_transaction.modified):
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
            elif new_transaction.locked:
                log_data['action'] = LOG_ACTIONS.LOCKED
                Log.objects.create(**log_data)
