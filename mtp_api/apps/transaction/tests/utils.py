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


def random_string(N=10):
    return get_random_string(
        length=N,
        allowed_chars=string.ascii_uppercase + string.digits
    )


def generate_transactions(uploads=2, transaction_batch=30):
    transactions = []
    for upload_counter in range(1, uploads+1):
        for transaction_counter in range(1, transaction_batch+1):
            data = {
                'upload_counter': upload_counter,
                'amount': random.randint(1000, 30000),
                'reference': random_string(),
                'received_at': timezone.now() - datetime.timedelta(
                    minutes=random.randint(0, 10000)
                )
            }

            # just making sure that valid transactions are selected
            # more othen than the ones in error
            if random.randint(1, 100) < 80:
                data.update({
                    'prison': Prison.objects.order_by('?').first(),
                    'prisoner_number': random_string(),
                    'prisoner_name': names.get_full_name(),
                    'prisoner_dob': random_dob()
                })
            if random.randint(1, 100) < 80:
                data.update({
                    'sender_bank_reference': random_string(),
                    'sender_customer_reference': random_string()
                })
            trans = Transaction.objects.create(**data)
            transactions.append(trans)
    return transactions
