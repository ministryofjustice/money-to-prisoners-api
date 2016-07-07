import datetime
from itertools import cycle
import random
import uuid

from django.utils import timezone
from faker import Faker

from core.tests.utils import MockModelTimestamps
from credit.constants import CREDIT_STATUS, CREDIT_RESOLUTION
from credit.models import Credit
from credit.tests.utils import (
    get_owner_and_status_chooser, create_credit_log, random_amount
)
from payment.constants import PAYMENT_STATUS
from payment.models import Payment
from prison.tests.utils import (
    random_prisoner_number, random_prisoner_dob,
    random_prisoner_name, get_prisoner_location_creator,
    load_nomis_prisoner_locations
)

fake = Faker(locale='en_GB')


def latest_payment_date():
    return timezone.now()


def generate_initial_payment_data(tot=50,
                                  prisoner_location_generator=None,
                                  number_of_prisoners=50,
                                  days_of_history=7):

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

    data_list = []
    for i in range(1, tot+1):
        random_date = latest_payment_date() - datetime.timedelta(
            minutes=random.randint(0, 1440*days_of_history)
        )
        random_date = timezone.localtime(random_date)
        amount = random_amount()
        prisoner = next(prisoners)
        data = {
            'amount': amount,
            'service_charge': int(amount * 0.025),
            'prisoner_name': prisoner['prisoner_name'],
            'prisoner_number': prisoner['prisoner_number'],
            'prisoner_dob': prisoner['prisoner_dob'],
            'recipient_name': prisoner['prisoner_name'],
            'email': fake.email(),
            'created': random_date,
            'modified': random_date,
        }
        data_list.append(data)

    return data_list


def generate_payments(payment_batch=50,
                      use_test_nomis_prisoners=False,
                      only_new_payments=False,
                      consistent_history=False,
                      days_of_history=7):

    if use_test_nomis_prisoners:
        prisoner_location_generator = cycle(load_nomis_prisoner_locations())
    else:
        prisoner_location_generator = None
    data_list = generate_initial_payment_data(
        tot=payment_batch,
        prisoner_location_generator=prisoner_location_generator,
        days_of_history=days_of_history
    )

    location_creator = get_prisoner_location_creator()
    if only_new_payments:
        def owner_status_chooser(*args):
            return None, CREDIT_STATUS.AVAILABLE
    else:
        owner_status_chooser = get_owner_and_status_chooser()

    payments = []
    for payment_counter, data in enumerate(data_list, start=1):
        new_payment = setup_payment(
            location_creator, owner_status_chooser,
            latest_payment_date(), payment_counter, data
        )
        payments.append(new_payment)

    generate_payment_logs(payments)

    return payments


def setup_payment(location_creator, owner_status_chooser,
                  end_date, payment_counter, data):
    _, prisoner_location = location_creator(
        data.get('prisoner_name'), data.get('prisoner_number'),
        data.get('prisoner_dob'), data.get('prison'),
    )

    incomplete = payment_counter % 10
    is_most_recent = data['created'].date() >= end_date.date()
    if incomplete:
        prison = prisoner_location.prison
        owner, status = owner_status_chooser(prison)
        data['prison'] = prison
        data['processor_id'] = str(uuid.uuid1())
        data['status'] = PAYMENT_STATUS.TAKEN
        if is_most_recent:
            data.update({
                'owner': None,
                'credited': False
            })
        else:
            data.update({
                'owner': owner,
                'credited': True,
                'reconciled': True
            })
    else:
        data['status'] = PAYMENT_STATUS.PENDING

    with MockModelTimestamps(data['created'], data['modified']):
        new_payment = save_payment(data)

    return new_payment


def save_payment(data):
    if data['status'] == PAYMENT_STATUS.TAKEN:
        if data.pop('credited', False):
            resolution = CREDIT_RESOLUTION.CREDITED
        else:
            resolution = CREDIT_RESOLUTION.PENDING
    else:
        resolution = CREDIT_RESOLUTION.INITIAL

    prisoner_dob = data.pop('prisoner_dob', None)
    prisoner_number = data.pop('prisoner_number', None)
    prisoner_name = data.pop('prisoner_name', None)
    prison = data.pop('prison', None)
    reconciled = data.pop('reconciled', False)
    owner = data.pop('owner', None)

    credit = Credit(
        amount=data['amount'],
        prisoner_dob=prisoner_dob,
        prisoner_number=prisoner_number,
        prisoner_name=prisoner_name,
        prison=prison,
        reconciled=reconciled,
        owner=owner,
        received_at=data['created'],
        resolution=resolution
    )
    credit.save()
    data['credit'] = credit

    return Payment.objects.create(**data)


def generate_payment_logs(payments):
    for new_payment in payments:
        if new_payment.credit:
            create_credit_log(new_payment.credit,
                              new_payment.modified,
                              new_payment.modified)
