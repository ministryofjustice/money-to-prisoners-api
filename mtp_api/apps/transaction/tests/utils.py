import datetime
import random
import names
import string

from django.utils import timezone
from django.utils.crypto import get_random_string

from prison.models import Prison
from ..models import Transaction


def random_dob():
    return datetime.date(
        day=random.randint(1, 29),
        month=random.randint(1, 12),
        year=random.randint(1930, 1990)
    )


def random_prison_number():
    # format: [A-Z]\d{4}[A-Z]{2}
    return '%s%s%s' % (
        get_random_string(allowed_chars=string.ascii_uppercase, length=1),
        get_random_string(allowed_chars=string.digits, length=4),
        get_random_string(allowed_chars=string.ascii_uppercase, length=2)
    )


def random_reference(prisoner_number=None, prisoner_dob=None):
    if not prisoner_number or not prisoner_dob:
        return get_random_string(length=15)
    return '%s %s' % (
        prisoner_number.lower(),
        prisoner_dob.strftime('%d%b%Y').lower()
    )


def generate_transactions(uploads=2, transaction_batch=30):
    transactions = []

    for upload_counter in range(1, uploads+1):
        for transaction_counter in range(1, transaction_batch+1):
            # Records might not have prisoner data and/or might not
            # have sender data.
            # Atm, we set the probability of it having either of them
            # to 80% which is an arbitrary high value as we expect
            # records to have correct data most of the time.
            include_prisoner_info = random.randint(0, 100) < 80
            include_sender_info = random.randint(0, 100) < 80

            data = {
                'upload_counter': upload_counter,
                'amount': random.randint(1000, 30000),
                'prison': None,
                'received_at': timezone.now() - datetime.timedelta(
                    minutes=random.randint(0, 10000)
                ),
            }

            if include_prisoner_info:
                data.update({
                    'prison': Prison.objects.order_by('?').first(),
                    'prisoner_number': random_prison_number(),
                    'prisoner_name': names.get_full_name(),
                    'prisoner_dob': random_dob()
                })
            if include_sender_info:
                data.update({
                    'sender_bank_reference': get_random_string(),
                    'sender_customer_reference': get_random_string()
                })

            data['reference'] = random_reference(
                data.get('prisoner_number'), data.get('prisoner_dob')
            )
            trans = Transaction.objects.create(**data)
            transactions.append(trans)
    return transactions
