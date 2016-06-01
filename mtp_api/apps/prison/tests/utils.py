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
    # format: A\d{4}[A-Z]{2}
    return 'A%s%s' % (
        get_random_string(allowed_chars='0123456789', length=4),
        get_random_string(allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ', length=2)
    )


def random_prisoner_name():
    name = '%s %s' % (fake.first_name_female() if random.random() > 0.8 else fake.first_name_male(),
                      fake.last_name())
    return name.upper()


def load_nomis_prisoner_locations():
    """
    Load prisoner locations matching test NOMIS data
    """
    csv_path = os.path.join(os.path.dirname(__file__), os.path.pardir,
                            'fixtures', 'test_nomis_prisoner_locations.csv')
    with open(csv_path) as f:
        csv_reader = csv.DictReader(f)
        prisoner_locations = list(csv_reader)
    for prisoner_location in prisoner_locations:
        prisoner_location['prisoner_dob'] = parse_date(prisoner_location['prisoner_dob'])
    return prisoner_locations


def get_prisoner_location_creator():
    """
    Returns a function(prisoner_name, prisoner_number, prisoner_dob) which when called returns:
        (is_valid, PrisonerLocation instance)
    """
    prisons = cycle(Prison.objects.all())
    index = cycle(range(0, 10))

    created_by = get_user_model().objects.first()

    def make_prisoner_location(prisoner_name, prisoner_number, prisoner_dob, prison=None):
        if not prisoner_number or not prisoner_dob:
            return False, None

        try:
            # if a prisoner with given number exists, then return known instance
            # this happens when using the sample set of NOMIS data
            return True, PrisonerLocation.objects.get(prisoner_number=prisoner_number)
        except PrisonerLocation.DoesNotExist:
            pass

        is_invalid = next(index) % 10 == 0  # 10% invalid

        if isinstance(prison, str):
            prison = Prison.objects.get(nomis_id=prison)
        elif not isinstance(prison, Prison):
            prison = next(prisons)

        data = {
            'created_by': created_by,
            'prisoner_name': prisoner_name,
            'prisoner_number': prisoner_number,
            'prisoner_dob': prisoner_dob,
            'prison': prison,
        }

        if is_invalid:
            data['prisoner_dob'] = data['prisoner_dob'] + datetime.timedelta(days=1)

        return not is_invalid, PrisonerLocation.objects.create(**data)

    return make_prisoner_location


def generate_predefined_prisoner_locations():
    """
    Used to make known prisoner locations for the "random transaction" scenario
    such that automated testing can be performed on them. Currently, doesn't
    link any transactions to them. NB: prisons themselves may not be stable
    """
    created_by = get_user_model().objects.first()
    prisons = cycle(Prison.objects.all())
    predefined_prisoner_locations = [
        {
            'prisoner_name': 'JAMES HALLS',
            'prisoner_number': 'A1409AE',
            'prisoner_dob': datetime.date(1989, 1, 21),
            'prison': next(prisons),
        },
        {
            'prisoner_name': 'RICKIE RIPPIN',
            'prisoner_number': 'A1617FY',
            'prisoner_dob': datetime.date(1975, 6, 30),
            'prison': next(prisons),
        },
    ]

    def mapper(_location):
        _location['created_by'] = created_by
        return _location

    predefined_prisoner_locations = map(mapper, predefined_prisoner_locations)
    for predefined_prisoner_location in predefined_prisoner_locations:
        PrisonerLocation.objects.create(**predefined_prisoner_location)
