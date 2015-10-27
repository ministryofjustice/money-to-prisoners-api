import datetime
from itertools import cycle
import string
import random

from django.contrib.auth.models import User
from django.utils.crypto import get_random_string
from faker import Faker

from prison.models import Prison, PrisonerLocation

fake = Faker(locale='en_GB')


def random_prisoner_dob():
    return fake.date_time_between(start_date='-85y', end_date='-20y').date()


def random_prisoner_number():
    # format: [A-Z]\d{4}[A-Z]{2}
    return '%s%s%s' % (
        get_random_string(allowed_chars=string.ascii_uppercase, length=1),
        get_random_string(allowed_chars=string.digits, length=4),
        get_random_string(allowed_chars=string.ascii_uppercase, length=2)
    )


def random_prisoner_name():
    return '%s %s' % (fake.first_name_female() if random.random() > 0.8 else fake.first_name_male(),
                      fake.last_name())


def get_prisoner_location_creator():
    """
    Returns a function(prisoner_number, prisoner_dob) which when called returns:
        (is_valid, PrisonerLocation instance)
    """
    prisons = cycle(list(Prison.objects.all()))
    # index = cycle(range(1, 11))

    created_by = User.objects.all()[0]

    def make_prisoner_location(prisoner_name, prisoner_number, prisoner_dob):
        if not prisoner_number or not prisoner_dob:
            return False, None

        # is_invalid = next(index) % 10 == 0  # 10% invalid (not implemented yet)
        is_invalid = False

        data = {
            'created_by': created_by,
            'prisoner_name': prisoner_name,
            'prisoner_number': prisoner_number,
            'prisoner_dob': prisoner_dob,
            'prison': next(prisons)
        }

        if is_invalid:
            data['prisoner_dob'] = data['prisoner_dob'] + datetime.timedelta(days=1)

        return not is_invalid, PrisonerLocation.objects.create(**data)

    return make_prisoner_location
