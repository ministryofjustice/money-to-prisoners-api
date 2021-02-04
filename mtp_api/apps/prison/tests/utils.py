import csv
import datetime
from itertools import cycle
import os
import random

from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.utils.dateparse import parse_date
from faker import Faker

from prison.models import Prison, PrisonerLocation

fake = Faker(locale='en_GB')


def random_prisoner_dob():
    return fake.date_time_between(start_date='-85y', end_date='-20y').date()


def random_prisoner_number():
    # format: 98% A\d{4}[A-Z]{2} and 2% [B-Z]\d{4}[A-Z]{2}
    return (
        (get_random_string(allowed_chars='BCDEFGHIJKLMNOPQRSTUVWXYZ', length=1) if random.random() > 0.98 else 'A') +
        get_random_string(allowed_chars='0123456789', length=4) +
        get_random_string(allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ', length=2)
    )


def random_prisoner_name():
    name = '%s %s' % (fake.first_name_female() if random.random() > 0.8 else fake.first_name_male(),
                      fake.last_name())
    return name.upper()


def load_random_prisoner_locations(number_of_prisoners=50):
    prisons = cycle(Prison.objects.all())
    prisoner_locations = generate_predefined_prisoner_locations()
    prisoner_locations += [
        {
            'created_by': get_user_model().objects.first(),
            'prisoner_name': random_prisoner_name(),
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'prison': next(prisons),
            'active': True,
        } for _ in range(number_of_prisoners - 2)
    ]
    return PrisonerLocation.objects.bulk_create(
        map(lambda data: PrisonerLocation(**data), prisoner_locations)
    )


def load_prisoner_locations_from_file(filename):
    """
    Load prisoner locations matching test NOMIS data
    """

    csv_path = os.path.join(os.path.dirname(__file__), os.path.pardir, 'fixtures', filename)
    with open(csv_path) as f:
        csv_reader = csv.DictReader(f)
        prisoner_locations = list(csv_reader)
    for prisoner_location in prisoner_locations:
        prisoner_location['created_by'] = get_user_model().objects.first(),
        prisoner_location['prison'] = Prison.objects.get(nomis_id=prisoner_location['prison'])
        prisoner_location['prisoner_dob'] = parse_date(prisoner_location['prisoner_dob'])
        prisoner_location['active'] = True

    return PrisonerLocation.objects.bulk_create(
        map(lambda data: PrisonerLocation(**data), prisoner_locations)
    )


def generate_predefined_prisoner_locations():
    """
    Used to make known prisoner locations for the "random transaction" scenario
    such that automated testing can be performed on them. Currently, doesn't
    link any transactions to them. NB: prisons themselves may not be stable
    """

    created_by = get_user_model().objects.first()

    prisons = cycle(Prison.objects.all())
    return [
        {
            'created_by': created_by,
            'prisoner_name': 'JAMES HALLS',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': datetime.date(1989, 1, 21),
            'prison': next(prisons),
            'active': True,
        },
        {
            'created_by': created_by,
            'prisoner_name': 'RICKIE RIPPIN',
            'prisoner_number': 'A1617FY',
            'prisoner_dob': datetime.date(1975, 6, 30),
            'prison': next(prisons),
            'active': True,
        },
    ]
