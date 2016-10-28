import datetime
from itertools import cycle
import random
import uuid

from django.utils import timezone
from faker import Faker

from core.tests.utils import MockModelTimestamps
from credit.constants import CREDIT_RESOLUTION
from credit.models import Credit
from credit.tests.utils import (
    get_owner_and_status_chooser, create_credit_log, random_amount
)
from payment.constants import PAYMENT_STATUS
from payment.models import Payment
from prison.models import PrisonerLocation

fake = Faker(locale='en_GB')


def latest_payment_date():
    return timezone.now()


def generate_initial_payment_data(tot=50,
                                  days_of_history=7):

    prisoners = cycle(list(PrisonerLocation.objects.all()))

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
            'prisoner_name': prisoner.prisoner_name,
            'prisoner_number': prisoner.prisoner_number,
            'prisoner_dob': prisoner.prisoner_dob,
            'prison': prisoner.prison,
            'recipient_name': prisoner.prisoner_name,
            'email': fake.email(),
            'created': random_date,
            'modified': random_date,
        }
        data_list.append(data)

    return data_list


def generate_payments(payment_batch=50,
                      consistent_history=False,
                      days_of_history=7):

    data_list = generate_initial_payment_data(
        tot=payment_batch,
        days_of_history=days_of_history
    )

    owner_status_chooser = get_owner_and_status_chooser()
    payments = []
    for payment_counter, data in enumerate(data_list, start=1):
        new_payment = setup_payment(
            owner_status_chooser,
            latest_payment_date(), payment_counter, data
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


def setup_payment(owner_status_chooser,
                  end_date, payment_counter, data):
    complete = bool(payment_counter % 10)
    older_than_yesterday = (
        data['created'].date() < (end_date.date() - datetime.timedelta(days=1))
    )
    if complete:
        owner, status = owner_status_chooser(data['prison'])
        data['processor_id'] = str(uuid.uuid1())
        data['status'] = PAYMENT_STATUS.TAKEN
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
            create_credit_log(new_payment.credit, new_payment.modified, new_payment.modified)
