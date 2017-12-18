from datetime import timedelta
from itertools import cycle
from math import ceil
import random

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.crypto import get_random_string
from faker import Faker

from core.tests.utils import MockModelTimestamps
from credit.tests.utils import random_amount, build_sender_prisoner_pairs
from disbursement.constants import (
    DISBURSEMENT_METHOD, DISBURSEMENT_RESOLUTION, LOG_ACTIONS
)
from disbursement.models import Disbursement, Log
from prison.models import PrisonerLocation

User = get_user_model()
fake = Faker(locale='en_GB')


def latest_disbursement_date():
    return timezone.now()


def get_recipient_prisoner_pairs():
    number_of_prisoners = PrisonerLocation.objects.all().count()
    number_of_recipients = number_of_prisoners
    number_of_sort_codes = int(ceil(number_of_recipients / 5))

    sort_codes = [
        get_random_string(6, '1234567890') for _ in range(number_of_sort_codes)
    ]
    recipients = []
    for i in range(number_of_recipients):
        recipient = {
            'method': (
                DISBURSEMENT_METHOD.BANK_TRANSFER if i % 4
                else DISBURSEMENT_METHOD.CHEQUE
            )
        }

        first_name = fake.first_name()
        last_name = fake.last_name()
        address_parts = fake.address().split('\n')
        if len(address_parts) == 4:
            recipient['address_line1'] = address_parts[0]
            recipient['address_line2'] = address_parts[1]
            recipient['city'] = address_parts[2]
            recipient['postcode'] = address_parts[3]
            recipient['country'] = 'UK'
        elif len(address_parts) == 3:
            recipient['address_line1'] = address_parts[0]
            recipient['city'] = address_parts[1]
            recipient['postcode'] = address_parts[2]
            recipient['country'] = 'UK'
        recipient['recipient_first_name'] = first_name
        recipient['recipient_last_name'] = last_name

        if i % 3:
            recipient['recipient_email'] = '%s.%s@mail.local' % (first_name, last_name)

        if recipient['method'] == DISBURSEMENT_METHOD.BANK_TRANSFER:
            recipient['sort_code'] = sort_codes[i % number_of_sort_codes]
            recipient['account_number'] = get_random_string(8, '1234567890')
        recipients.append(recipient)

    prisoners = list(PrisonerLocation.objects.all())

    recipient_prisoner_pairs = build_sender_prisoner_pairs(recipients, prisoners)
    return cycle(recipient_prisoner_pairs)


def generate_initial_disbursement_data(tot=100, days_of_history=7):
    data_list = []
    recipient_prisoner_pairs = get_recipient_prisoner_pairs()
    for _ in range(tot):
        random_date = latest_disbursement_date() - timedelta(
            minutes=random.randint(0, 1440 * days_of_history)
        )
        random_date = timezone.localtime(random_date)
        amount = random_amount()
        recipient, prisoner = next(recipient_prisoner_pairs)
        data = {
            'amount': amount,
            'prisoner_number': prisoner.prisoner_number,
            'prison': prisoner.prison,
            'created': random_date
        }
        data.update(recipient)
        data_list.append(data)

    return data_list


def generate_disbursements(disbursement_batch=100, days_of_history=7):
    data_list = generate_initial_disbursement_data(disbursement_batch, days_of_history)
    return create_disbursements(data_list)


def create_disbursements(data_list):
    disbursements = []
    for disbursement_counter, data in enumerate(data_list, start=1):
        new_disbursement = setup_disbursement(
            latest_disbursement_date(), disbursement_counter, data
        )
        disbursements.append(new_disbursement)
    return disbursements


def setup_disbursement(end_date, disbursement_counter, data):
    if disbursement_counter % 20 == 0:
        data['resolution'] = DISBURSEMENT_RESOLUTION.REJECTED
        data['modified'] = data['created'] + timedelta(hours=3)
    elif data['created'].date() < latest_disbursement_date().date() - timedelta(days=1):
        data['resolution'] = DISBURSEMENT_RESOLUTION.SENT
        data['modified'] = data['created'] + timedelta(days=1)
    elif data['created'].date() < latest_disbursement_date().date() - timedelta(hours=4):
        data['resolution'] = DISBURSEMENT_RESOLUTION.CONFIRMED
        data['modified'] = data['created'] + timedelta(hours=3)
    else:
        data['modified'] = data['created']

    with MockModelTimestamps(data['created'], data['modified']):
        new_disbursement = Disbursement.objects.create(**data)

    create_disbursement_logs(new_disbursement)
    return new_disbursement


def create_disbursement_logs(disbursement):
    log_data = {
        'disbursement': disbursement,
    }

    prison_clerks = User.objects.filter(
        groups__name='PrisonClerk',
        prisonusermapping__prisons=disbursement.prison
    )
    bank_admins = User.objects.filter(groups__name='BankAdmin')

    creating_user = prison_clerks.first()

    with MockModelTimestamps(disbursement.created, disbursement.created):
        log_data['action'] = LOG_ACTIONS.CREATED
        log_data['user'] = creating_user
        Log.objects.create(**log_data)

    confirming_user = prison_clerks.last()

    if disbursement.resolution == DISBURSEMENT_RESOLUTION.SENT:
        sending_user = bank_admins.first()
        confirmed = disbursement.created - timedelta(hours=3)
        with MockModelTimestamps(confirmed, confirmed):
            log_data['action'] = LOG_ACTIONS.CONFIRMED
            log_data['user'] = confirming_user
            Log.objects.create(**log_data)
        with MockModelTimestamps(disbursement.modified, disbursement.modified):
            log_data['action'] = LOG_ACTIONS.SENT
            log_data['user'] = sending_user
            Log.objects.create(**log_data)
    else:
        with MockModelTimestamps(disbursement.modified, disbursement.modified):
            if disbursement.resolution == DISBURSEMENT_RESOLUTION.CONFIRMED:
                log_data['action'] = LOG_ACTIONS.CONFIRMED
                log_data['user'] = confirming_user
                Log.objects.create(**log_data)
            elif disbursement.resolution == DISBURSEMENT_RESOLUTION.REJECTED:
                log_data['action'] = LOG_ACTIONS.REJECTED
                log_data['user'] = confirming_user
                Log.objects.create(**log_data)
