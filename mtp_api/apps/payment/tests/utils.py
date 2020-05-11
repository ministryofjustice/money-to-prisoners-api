import datetime
from itertools import cycle
import random
import uuid

from django.utils import timezone
from django.utils.crypto import get_random_string
from faker import Faker

from core.tests.utils import MockModelTimestamps
from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from credit.tests.utils import (
    get_owner_and_status_chooser, create_credit_log, random_amount,
    build_sender_prisoner_pairs,
)
from payment.constants import PAYMENT_STATUS
from payment.models import Payment, BillingAddress
from prison.models import PrisonerLocation

fake = Faker(locale='en_GB')


def latest_payment_date():
    return timezone.now()


def get_sender_prisoner_pairs():
    number_of_prisoners = PrisonerLocation.objects.all().count()
    number_of_senders = number_of_prisoners

    senders = []
    for _ in range(number_of_senders):
        expiry_date = fake.date_time_between(start_date='now', end_date='+5y')
        full_name = ' '.join([fake.first_name(), fake.last_name()])
        address_parts = fake.address().split('\n')
        billing_address = {}
        if len(address_parts) == 4:
            billing_address = {
                'line1': address_parts[0],
                'line2': address_parts[1],
                'city': address_parts[2],
                'postcode': address_parts[3],
                'country': 'UK',
            }
        elif len(address_parts) == 3:
            billing_address = {
                'line1': address_parts[0],
                'city': address_parts[1],
                'postcode': address_parts[2],
                'country': 'UK',
            }
        senders.append(
            {
                'cardholder_name': full_name,
                'card_number_first_digits': get_random_string(6, '0123456789'),
                'card_number_last_digits': get_random_string(4, '0123456789'),
                'card_expiry_date': expiry_date.strftime('%m/%y'),
                'ip_address': fake.ipv4(),
                'email': '%s@mail.local' % full_name.replace(' ', '.'),
                'card_brand': 'Visa',
                'billing_address': billing_address,
            }
        )

    prisoners = list(PrisonerLocation.objects.all())

    sender_prisoner_pairs = build_sender_prisoner_pairs(senders, prisoners)
    return cycle(sender_prisoner_pairs)


def generate_initial_payment_data(tot=50, days_of_history=7):
    data_list = []
    sender_prisoner_pairs = get_sender_prisoner_pairs()
    for _ in range(tot):
        random_date = latest_payment_date() - datetime.timedelta(
            minutes=random.randint(0, 1440 * days_of_history)
        )
        random_date = timezone.localtime(random_date)
        amount = random_amount()
        sender, prisoner = next(sender_prisoner_pairs)
        data = {
            'amount': amount,
            'service_charge': int(amount * 0.025),
            'prisoner_name': prisoner.prisoner_name,
            'prisoner_number': prisoner.prisoner_number,
            'single_offender_id': prisoner.single_offender_id,
            'prisoner_dob': prisoner.prisoner_dob,
            'prison': prisoner.prison,
            'recipient_name': prisoner.prisoner_name,
            'created': random_date,
            'modified': random_date,
        }
        data.update(sender)
        data_list.append(data)

    return data_list


def generate_payments(payment_batch=50, consistent_history=False, days_of_history=7, overrides=None):
    data_list = generate_initial_payment_data(
        tot=payment_batch,
        days_of_history=days_of_history
    )
    return create_payments(data_list, consistent_history, overrides)


# TODO consistent_history doesn't seem to do anything, yet is provided by some calling functions...
def create_payments(data_list, consistent_history=False, overrides=None):
    owner_status_chooser = get_owner_and_status_chooser()
    payments = []
    for payment_counter, data in enumerate(data_list, start=1):
        new_payment = setup_payment(
            owner_status_chooser,
            latest_payment_date(),
            payment_counter,
            data,
            overrides
        )
        payments.append(new_payment)

    generate_payment_logs(payments)

    earliest_payment = Payment.objects.all().order_by('credit__received_at').first()
    if earliest_payment:
        reconciliation_date = earliest_payment.credit.received_at.date()
        while reconciliation_date < latest_payment_date().date() - datetime.timedelta(days=1):
            start_date = datetime.datetime.combine(
                reconciliation_date,
                datetime.time(0, 0, tzinfo=timezone.utc)
            )
            end_date = datetime.datetime.combine(
                reconciliation_date + datetime.timedelta(days=1),
                datetime.time(0, 0, tzinfo=timezone.utc)
            )
            Payment.objects.reconcile(start_date, end_date, None)
            reconciliation_date += datetime.timedelta(days=1)
    return payments


def setup_payment(owner_status_chooser, end_date, payment_counter, data, overrides=None):
    older_than_yesterday = (
        data['created'].date() < (end_date.date() - datetime.timedelta(days=1))
    )
    if overrides and overrides.get('status'):
        data['status'] = overrides['status']
    elif not bool(payment_counter % 11):  # 1 in 11 is expired
        data['status'] = PAYMENT_STATUS.EXPIRED
    elif not bool(payment_counter % 10):  # 1 in 10 is rejected
        data['status'] = PAYMENT_STATUS.REJECTED
    elif not bool(payment_counter % 4):  # 1 in 4ish is pending
        data['status'] = PAYMENT_STATUS.PENDING
    else:  # otherwise it's taken
        data['status'] = PAYMENT_STATUS.TAKEN

    if data['status'] == PAYMENT_STATUS.PENDING:
        del data['cardholder_name']
        del data['card_number_first_digits']
        del data['card_number_last_digits']
        del data['card_expiry_date']
        del data['card_brand']
        del data['billing_address']
    elif data['status'] == PAYMENT_STATUS.TAKEN:
        owner, status = owner_status_chooser(data['prison'])
        data['processor_id'] = str(uuid.uuid1())
        # TODO This is a horrible piece of implicit logic, can we please make it explicit
        # or document it somewhere
        if older_than_yesterday:
            data.update({
                'owner': owner,
                'credited': True
            })
        else:
            data.update({
                'owner': None,
                'credited': False
            })

    if overrides:
        data.update(overrides)
    with MockModelTimestamps(data['created'], data['modified']):
        new_payment = save_payment(data)

    return new_payment


def save_payment(data):
    is_taken = data['status'] == PAYMENT_STATUS.TAKEN
    if is_taken:
        if data.pop('credited', False):
            resolution = CREDIT_RESOLUTION.CREDITED
        else:
            resolution = CREDIT_RESOLUTION.PENDING
    elif data['status'] in (PAYMENT_STATUS.REJECTED, PAYMENT_STATUS.EXPIRED):
        resolution = CREDIT_RESOLUTION.FAILED
    else:
        resolution = CREDIT_RESOLUTION.INITIAL

    prisoner_dob = data.pop('prisoner_dob', None)
    prisoner_number = data.pop('prisoner_number', None)
    single_offender_id = data.pop('single_offender_id', None)
    prisoner_name = data.pop('prisoner_name', None)
    prison = data.pop('prison', None)
    reconciled = data.pop('reconciled', False)
    owner = data.pop('owner', None)

    billing_address = data.pop('billing_address', None)
    if billing_address:
        billing_address = BillingAddress.objects.create(**billing_address)
        data['billing_address'] = billing_address

    credit = Credit(
        amount=data['amount'],
        prisoner_dob=prisoner_dob,
        prisoner_number=prisoner_number,
        single_offender_id=single_offender_id,
        prisoner_name=prisoner_name,
        prison=prison,
        reconciled=False if not is_taken else reconciled,
        owner=owner,
        received_at=None if not is_taken else data['created'],
        resolution=resolution,
    )
    credit.save()
    data['credit'] = credit

    return Payment.objects.create(**data)


def generate_payment_logs(payments):
    for new_payment in payments:
        if new_payment.credit:
            create_credit_log(new_payment.credit, new_payment.modified, new_payment.modified)
