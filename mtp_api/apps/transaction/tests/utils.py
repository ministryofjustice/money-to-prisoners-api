import datetime
import random

from django.utils import timezone
from django.utils.crypto import get_random_string

from prison.models import Prison

from transaction.models import Transaction
from transaction.constants import TRANSACTION_STATUS


from prison.tests.utils import random_prisoner_number, random_prisoner_dob


def random_reference(prisoner_number=None, prisoner_dob=None):
    if not prisoner_number or not prisoner_dob:
        return get_random_string(length=15)
    return '%s %s' % (
        prisoner_number.lower(),
        prisoner_dob.strftime('%d%b%Y').lower()
    )


def generate_transactions_data(uploads=2, transaction_batch=50, status=None):
    data_list = []

    class PrisonChooser(object):

        def __init__(self):
            self.prisons = Prison.objects.all()
            self.clerks_per_prison = {}
            for prison in self.prisons:
                self.clerks_per_prison[prison.pk] = {
                    'users': prison.prisonusermapping_set.values_list('user', flat=True),
                    'index': 0
                }
            self.index = 0

        def _choose(self, l, index):
            item = l[index]
            index += 1
            if index >= len(l):
                index = 0
            return (item, index)

        def choose_prison(self):
            prison, index = self._choose(self.prisons, self.index)
            self.index = index
            return prison

        def choose_user(self, prison):
            data = self.clerks_per_prison[prison.pk]
            user, index = self._choose(data['users'], data['index'])
            data['index'] = index
            return user

    prison_chooser = PrisonChooser()

    now = timezone.now().replace(microsecond=0)

    for upload_counter in range(1, uploads+1):
        for transaction_counter in range(1, transaction_batch+1):
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
                'upload_counter': upload_counter,
                'amount': random.randint(1000, 30000),
                'prison': None,
                'received_at': now - datetime.timedelta(
                    minutes=random.randint(0, 10000)
                ),
                'sender_sort_code': get_random_string(6, '1234567890'),
                'sender_account_number': get_random_string(8, '1234567890'),
                'sender_name': get_random_string(10)
            }

            if include_prisoner_info:
                prison = prison_chooser.choose_prison()
                data.update({
                    'prison': prison,
                    'prisoner_number': random_prisoner_number(),
                    'prisoner_dob': random_prisoner_dob()
                })

                # randomly choose the state of the transaction
                trans_status = status
                if not trans_status:
                    trans_status = random.choice(
                        [
                            TRANSACTION_STATUS.LOCKED,
                            TRANSACTION_STATUS.AVAILABLE,
                            TRANSACTION_STATUS.CREDITED
                        ]
                    )

                if trans_status == TRANSACTION_STATUS.LOCKED:
                    data.update({
                        'owner_id': prison_chooser.choose_user(prison),
                        'credited': False
                    })
                elif trans_status == TRANSACTION_STATUS.AVAILABLE:
                    data.update({
                        'owner': None,
                        'credited': False
                    })
                elif trans_status == TRANSACTION_STATUS.CREDITED:
                    data.update({
                        'owner_id': prison_chooser.choose_user(prison),
                        'credited': True
                    })
            else:
                if transaction_counter % 2 == 0:
                    data.update({'refunded': True})
                else:
                    data.update({'refunded': False})

            if include_sender_roll_number:
                data.update({
                    'sender_roll_number': get_random_string(15, '1234567890')
                })

            data['reference'] = random_reference(
                data.get('prisoner_number'), data.get('prisoner_dob')
            )
            data_list.append(data)
    return data_list


def generate_transactions(uploads=2, transaction_batch=30):
    data_list = generate_transactions_data(
        uploads=uploads, transaction_batch=transaction_batch
    )

    transactions = []
    for data in data_list:
        transactions.append(
            Transaction.objects.create(**data)
        )
    return transactions
