from oauth2_provider.models import Application

from django.contrib.auth.models import User

from mtp_auth.models import ApplicationUserMapping
from prison.models import Prison
from mtp_auth.tests.mommy_recipes import create_prison_user_mapping, \
    create_prisoner_location_admins, create_bank_admins, create_refund_bank_admins
from mtp_auth.constants import CASHBOOK_OAUTH_CLIENT_ID, \
    BANK_ADMIN_OAUTH_CLIENT_ID, PRISONER_LOCATION_OAUTH_CLIENT_ID


def make_test_users(clerks_per_prison=2):
    # prison clerks
    prison_clerks = []
    for prison in Prison.objects.all():
        for index in range(clerks_per_prison):
            pu = create_prison_user_mapping(prison)
            prison_clerks.append(pu.user)

    # prisoner location admin
    prisoner_location_admins = create_prisoner_location_admins()

    # bank admin
    bank_admins = create_bank_admins()
    refund_bank_admins = create_refund_bank_admins()

    # create test oauth applications
    user = User.objects.first()

    for client_id in [
        CASHBOOK_OAUTH_CLIENT_ID,
        BANK_ADMIN_OAUTH_CLIENT_ID,
        PRISONER_LOCATION_OAUTH_CLIENT_ID
    ]:
        Application.objects.get_or_create(
            client_id=client_id,
            client_type='confidential',
            authorization_grant_type='password',
            client_secret=client_id,
            name=client_id,
            user=user
        )

    def link_users_with_client(users, client_id):
        for user in users:
            ApplicationUserMapping.objects.get_or_create(
                user=user,
                application=Application.objects.get(client_id=client_id)
            )

    link_users_with_client(prison_clerks, CASHBOOK_OAUTH_CLIENT_ID)
    link_users_with_client(prisoner_location_admins, PRISONER_LOCATION_OAUTH_CLIENT_ID)
    link_users_with_client(bank_admins, BANK_ADMIN_OAUTH_CLIENT_ID)
    link_users_with_client(refund_bank_admins, BANK_ADMIN_OAUTH_CLIENT_ID)

    return (prison_clerks, prisoner_location_admins, bank_admins, refund_bank_admins)
