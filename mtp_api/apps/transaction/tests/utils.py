import datetime
from functools import partial
from itertools import cycle
import random
import warnings

from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone
from django.utils.crypto import get_random_string
from faker import Faker

from core.tests.utils import MockModelTimestamps
from credit.constants import CREDIT_RESOLUTION, CREDIT_STATUS
from credit.models import Credit
from credit.tests.utils import (
    get_owner_and_status_chooser, create_credit_log, random_amount
)
from prison.models import PrisonerLocation
from prison.tests.utils import (
    random_prisoner_number, random_prisoner_dob, random_prisoner_name,
    get_prisoner_location_creator, load_nomis_prisoner_locations
)
from transaction.models import Transaction
from transaction.constants import (
    TRANSACTION_CATEGORY, TRANSACTION_SOURCE
)

fake = Faker(locale='en_GB')


def random_sender_name():
    name = []
    # < 5% have a title
    if random.random() < 0.05:
        name.insert(0, random.choice(['MISS', 'MR', 'MRS']))
    # > 60% have an initial
    if random.random() > 0.6:
        name.append(random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
    else:
        name.append(fake.first_name().upper())
    surname = fake.last_name().upper()
    if random.random() > 0.5:
        name.append(surname)
    else:
        name.insert(0, surname)
    return ' '.join(name)


def random_reference(prisoner_number=None, prisoner_dob=None):
    if not prisoner_number or not prisoner_dob:
        return get_random_string(length=15)
    return '%s %s' % (
        prisoner_number.upper(),
        prisoner_dob.strftime('%d/%m/%Y'),
    )


def get_midnight(dt):
    return dt.tzinfo.localize(dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None))


def latest_transaction_date():
    latest_transaction_date = timezone.now().replace(microsecond=0) - datetime.timedelta(days=1)
    while latest_transaction_date.weekday() > 4:
        latest_transaction_date = latest_transaction_date - datetime.timedelta(days=1)
    return timezone.localtime(latest_transaction_date)


def generate_initial_transactions_data(
        tot=50,
        prisoner_location_generator=None,
        include_debits=True,
        include_administrative_credits=True,
        include_unidentified_credits=True,
        number_of_sort_codes=6,
        number_of_senders=20,
        number_of_prisoners=50):
    data_list = []
    sort_codes = [
        get_random_string(6, '1234567890') for _ in range(number_of_sort_codes)
    ]
    senders = [
        {
            'name': random_sender_name(),
            'sort_code': sort_codes[n % number_of_sort_codes],
            'account_number': get_random_string(8, '1234567890'),
            'roll_number': get_random_string(15, '1234567890')
        } for n in range(number_of_senders)
    ]

    if prisoner_location_generator:
        prisoners = prisoner_location_generator
    else:
        prisoners = cycle([
            {
                'prisoner_name': random_prisoner_name(),
                'prisoner_number': random_prisoner_number(),
                'prisoner_dob': random_prisoner_dob()
            } for n in range(number_of_prisoners)
        ])

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
        include_sender_roll_number = transaction_counter % 19 == 0
        omit_sender_details = (
            include_unidentified_credits and transaction_counter % 23 == 0
        )
        make_debit_transaction = (
            include_debits and (transaction_counter + 1) % 5 == 0
        )
        make_administrative_credit_transaction = (
            include_administrative_credits and transaction_counter % 41 == 0
        )

        random_date = latest_transaction_date() - datetime.timedelta(
            minutes=random.randint(0, 10000)
        )
        random_date = timezone.localtime(random_date)
        midnight_random_date = get_midnight(random_date)
        random_sender = random.choice(senders)
        data = {
            'category': TRANSACTION_CATEGORY.CREDIT,
            'amount': random_amount(),
            'received_at': midnight_random_date,
            'sender_sort_code': random_sender['sort_code'],
            'sender_account_number': random_sender['account_number'],
            'sender_name': random_sender['name'],
            'owner': None,
            'credited': False,
            'refunded': False,
            'created': random_date,
            'modified': random_date,
        }

        if make_administrative_credit_transaction:
            data['source'] = TRANSACTION_SOURCE.ADMINISTRATIVE
            data['incomplete_sender_info'] = True
            data['processor_type_code'] = 'RA'
            del data['sender_sort_code']
            del data['sender_account_number']
        elif make_debit_transaction:
            data['source'] = TRANSACTION_SOURCE.ADMINISTRATIVE
            data['category'] = TRANSACTION_CATEGORY.DEBIT
            data['processor_type_code'] = '03'
            data['reference'] = 'Payment refunded'
        else:
            data['source'] = TRANSACTION_SOURCE.BANK_TRANSFER
            data['processor_type_code'] = '99'

            if include_prisoner_info:
                data.update(next(prisoners))

            if include_sender_roll_number:
                data.update({
                    'sender_roll_number': random_sender['roll_number']
                })

            if omit_sender_details:
                data['incomplete_sender_info'] = True
                if data.get('sender_roll_number'):
                    del data['sender_roll_number']
                else:
                    del data['sender_account_number']
                    if transaction_counter % 2 == 0:
                        del data['sender_sort_code']

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
    over_a_week_ago = timezone.localtime(over_a_week_ago)
    a_week_ago = over_a_week_ago + datetime.timedelta(days=1)
    a_week_ago = timezone.localtime(a_week_ago)
    data = {
        'received_at': get_midnight(over_a_week_ago),
        'created': over_a_week_ago,
        'modified': a_week_ago,
        'owner': None,
        'credited': True,
        'refunded': False,

        'sender_name': 'Mary Stevenson',
        'amount': 7230,
        'category': TRANSACTION_CATEGORY.CREDIT,
        'source': TRANSACTION_SOURCE.BANK_TRANSFER,
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


def generate_transactions(
    transaction_batch=50,
    use_test_nomis_prisoners=False,
    predetermined_transactions=False,
    only_new_transactions=False,
    consistent_history=False,
    include_debits=True,
    include_administrative_credits=True,
    include_unidentified_credits=True
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
        include_unidentified_credits=include_unidentified_credits
    )

    location_creator = get_prisoner_location_creator()
    if only_new_transactions:
        def owner_status_chooser(*args):
            return None, CREDIT_STATUS.AVAILABLE
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
                new_transaction = save_transaction(data)
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
            data['prison'] = None
            data['prisoner_name'] = None
            if is_most_recent and not data.get('incomplete_sender_info'):
                data.update({'refunded': False})
            else:
                data.update({'refunded': True})

    with MockModelTimestamps(data['created'], data['modified']):
        new_transaction = save_transaction(data)

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
            if status == CREDIT_STATUS.LOCKED:
                data.update({
                    'owner': owner,
                    'credited': False
                })
            elif status == CREDIT_STATUS.AVAILABLE:
                data.update({
                    'owner': None,
                    'credited': False
                })
            elif status == CREDIT_STATUS.CREDITED:
                data.update({
                    'owner': owner,
                    'credited': True
                })
        else:
            data['prison'] = None
            data['prisoner_name'] = None
            if transaction_counter % 2 == 0 and not data.get('incomplete_sender_info'):
                data.update({'refunded': True})
            else:
                data.update({'refunded': False})

    with MockModelTimestamps(data['created'], data['modified']):
        new_transaction = save_transaction(data)

    return new_transaction


def save_transaction(data):
    if data.pop('credited', False):
        resolution = CREDIT_RESOLUTION.CREDITED
    elif data.pop('refunded', False):
        resolution = CREDIT_RESOLUTION.REFUNDED
    else:
        resolution = CREDIT_RESOLUTION.PENDING

    prisoner_dob = data.pop('prisoner_dob', None)
    prisoner_number = data.pop('prisoner_number', None)
    prisoner_name = data.pop('prisoner_name', None)
    prison = data.pop('prison', None)
    reconciled = data.pop('reconciled', False)
    owner = data.pop('owner', None)

    if (data['category'] == TRANSACTION_CATEGORY.CREDIT and
            data['source'] == TRANSACTION_SOURCE.BANK_TRANSFER):
        credit = Credit(
            amount=data['amount'],
            prisoner_dob=prisoner_dob,
            prisoner_number=prisoner_number,
            prisoner_name=prisoner_name,
            prison=prison,
            reconciled=reconciled,
            owner=owner,
            received_at=data['received_at'],
            resolution=resolution
        )
        credit.save()
        data['credit'] = credit

    return Transaction.objects.create(**data)


def generate_transaction_logs(transactions):
    for new_transaction in transactions:
        if new_transaction.credit:
            create_credit_log(new_transaction.credit,
                              new_transaction.modified,
                              new_transaction.modified)


def filters_from_api_data(data):
    filters = {}
    for field in data:
        try:
            Transaction._meta.get_field(field)
            filters[field] = data[field]
            if (data['category'] == TRANSACTION_CATEGORY.CREDIT and
                    data['source'] == TRANSACTION_SOURCE.BANK_TRANSFER):
                Credit._meta.get_field(field)
                filters['credit__%s' % field] = data[field]
        except FieldDoesNotExist:
            pass
    return filters
