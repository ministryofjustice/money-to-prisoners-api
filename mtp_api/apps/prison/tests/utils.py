import datetime
import random
import string

from django.utils.crypto import get_random_string


def random_prisoner_dob():
    return datetime.date(
        day=random.randint(1, 28),
        month=random.randint(1, 12),
        year=random.randint(1930, 1990)
    )


def random_prisoner_number():
    # format: [A-Z]\d{4}[A-Z]{2}
    return '%s%s%s' % (
        get_random_string(allowed_chars=string.ascii_uppercase, length=1),
        get_random_string(allowed_chars=string.digits, length=4),
        get_random_string(allowed_chars=string.ascii_uppercase, length=2)
    )
