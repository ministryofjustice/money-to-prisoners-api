import csv
import datetime
from itertools import cycle
import os
import random
import uuid

from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.utils.dateparse import parse_date
from faker import Faker

from prison.models import Prison, PrisonerLocation

fake = Faker(locale='en_GB')


def random_prisoner_dob():
    return fake.date_time_between(start_date='-85y', end_date='-20y').date()


def random_prisoner_number():
    # format: A\d{4}[A-Z]{2}
    return 'A%s%s' % (
        get_random_string(allowed_chars='0123456789', length=4),
        get_random_string(allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ', length=2)
    )


def random_prisoner_name():
    name = '%s %s' % (fake.first_name_female() if random.random() > 0.8 else fake.first_name_male(),
                      fake.last_name())
    return name.upper()


def load_random_prisoner_locations(number_of_prisoners=50, single_offender_id=True):
    if single_offender_id:
        extra_key = 'single_offender_id'
        extra_value = uuid.uuid4
    else:
        extra_key = 'created_by'
        extra_value = get_user_model().objects.first()
    prisons = cycle(Prison.objects.all())
    prisoner_locations = generate_predefined_prisoner_locations(single_offender_id=single_offender_id)
    prisoner_locations += [
        {
            extra_key: extra_value() if callable(extra_value) else extra_value,
            'prisoner_name': random_prisoner_name(),
            'prisoner_number': random_prisoner_number(),
            'prisoner_dob': random_prisoner_dob(),
            'prison': next(prisons),
            'active': True,
        } for _ in range(number_of_prisoners - 2)
    ]
    PrisonerLocation.objects.bulk_create(
        map(lambda data: PrisonerLocation(**data), prisoner_locations)
    )


def load_prisoner_locations_from_file(filename, single_offender_id=True):
    """
    Load prisoner locations matching test NOMIS data
    """
    if single_offender_id:
        extra_key = 'single_offender_id'
        extra_value = uuid.uuid4
    else:
        extra_key = 'created_by'
        extra_value = get_user_model().objects.first()
    csv_path = os.path.join(os.path.dirname(__file__), os.path.pardir, 'fixtures', filename)
    with open(csv_path) as f:
        csv_reader = csv.DictReader(f)
        prisoner_locations = list(csv_reader)
    for prisoner_location in prisoner_locations:
        prisoner_location[extra_key] = extra_value() if callable(extra_value) else extra_value
        prisoner_location['prison'] = Prison.objects.get(nomis_id=prisoner_location['prison'])
        prisoner_location['prisoner_dob'] = parse_date(prisoner_location['prisoner_dob'])
        prisoner_location['active'] = True

    PrisonerLocation.objects.bulk_create(
        map(lambda data: PrisonerLocation(**data), prisoner_locations)
    )


def generate_predefined_prisoner_locations(single_offender_id=True):
    """
    Used to make known prisoner locations for the "random transaction" scenario
    such that automated testing can be performed on them. Currently, doesn't
    link any transactions to them. NB: prisons themselves may not be stable
    """
    prisons = cycle(Prison.objects.all())
    predefined_prisoner_locations = [
        {
            'single_offender_id': '4a39e889-7abb-817c-e050-16ac01107c5c',
            'prisoner_name': 'JAMES HALLS',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': datetime.date(1989, 1, 21),
            'prison': next(prisons),
            'active': True,
        },
        {
            'single_offender_id': 'ddb96373-6273-4aba-b4f6-d14266a18ea1',
            'prisoner_name': 'RICKIE RIPPIN',
            'prisoner_number': 'A1617FY',
            'prisoner_dob': datetime.date(1975, 6, 30),
            'prison': next(prisons),
            'active': True,
        },
    ]
    if not single_offender_id:
        created_by = get_user_model().objects.first()
        for prisoner_locations in predefined_prisoner_locations:
            prisoner_locations['created_by'] = created_by
            del prisoner_locations['single_offender_id']
    return predefined_prisoner_locations
