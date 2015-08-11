from oauth2_provider.models import Application

from django.contrib.auth.models import User

from prison.models import Prison
from mtp_auth.tests.mommy_recipes import create_prison_user_mapping, \
    create_prisoner_location_admins


def make_test_users(users_per_prison=1):
    # prison clerks
    prison_clerks = []
    for prison in Prison.objects.all():
        for index in range(users_per_prison):
            pu = create_prison_user_mapping(prison)
            prison_clerks.append(pu.user)

    # prisoner location admin
    prisoner_location_admins = create_prisoner_location_admins()
    return (prison_clerks, prisoner_location_admins)


def make_test_oauth_applications():
    Application.objects.get_or_create(
        client_id='cashbook',
        client_type='confidential',
        authorization_grant_type='password',
        client_secret='cashbook',
        name='cashbook',
        user=User.objects.first()
    )

    Application.objects.get_or_create(
        client_id='prisoner-location-admin',
        client_type='confidential',
        authorization_grant_type='password',
        client_secret='prisoner-location-admin',
        name='prisoner-location-admin',
        user=User.objects.first()
    )
