from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from oauth2_provider.models import Application

from mtp_auth.constants import (
    CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, SEND_MONEY_CLIENT_ID
)
from mtp_auth.models import Role, ApplicationUserMapping, PrisonUserMapping
from mtp_auth.tests.mommy_recipes import (
    create_prison_clerk, create_prisoner_location_admin, create_bank_admin,
    create_refund_bank_admin, create_send_money_shared_user, create_user_admin,
    create_security_staff_user
)
from prison.models import Prison


class MockModelTimestamps:
    """
    Context manager to allow specifying the created and modified
    datetimes when saving models extending TimeStampedModel
    """

    def __init__(self, created=None, modified=None):
        self.patches = []
        if created:
            self.patches.append(
                mock.patch('model_utils.fields.AutoCreatedField.get_default',
                           return_value=created)
            )
        if modified:
            self.patches.append(
                mock.patch('model_utils.fields.now',
                           return_value=modified)
            )

    def __enter__(self):
        for patch in self.patches:
            patch.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        for patch in self.patches:
            patch.stop()


def make_applications():
    owner = get_user_model().objects.first()

    def make_application_and_roles(client_id, name, *roles):
        new_app, _ = Application.objects.get_or_create(
            client_id=client_id,
            client_type='confidential',
            authorization_grant_type='password',
            client_secret=client_id,
            name=name,
            user=owner,
        )
        for role in roles:
            groups = [Group.objects.get_or_create(name=group)[0] for group in role['groups']]
            key_group, groups = groups[0], groups[1:]
            role, _ = Role.objects.get_or_create(
                name=role['name'],
                application=new_app,
                key_group=key_group,
            )
            role.other_groups.set(groups)

    make_application_and_roles(
        CASHBOOK_OAUTH_CLIENT_ID, 'Digital cashbook',
        {'name': 'prison-clerk', 'groups': ['PrisonClerk']},
    )
    make_application_and_roles(
        NOMS_OPS_OAUTH_CLIENT_ID, 'Prisoner money intelligence',
        {'name': 'prisoner-location-admin', 'groups': ['PrisonerLocationAdmin']},
        {'name': 'security', 'groups': ['Security']},
    )
    make_application_and_roles(
        BANK_ADMIN_OAUTH_CLIENT_ID, 'Bank admin',
        {'name': 'bank-admin', 'groups': ['RefundBankAdmin', 'BankAdmin']},
    )
    make_application_and_roles(
        SEND_MONEY_CLIENT_ID, 'Send money to a prisoner',
    )

    Role.objects.get(name='prison-clerk').managed_roles.add(Role.objects.get(name='security'))


def give_superusers_full_access():
    super_admins = get_user_model().objects.filter(is_superuser=True)
    for super_admin in super_admins:
        mapping = PrisonUserMapping.objects.get_or_create(user=super_admin)[0]
        for prison in Prison.objects.all():
            mapping.prisons.add(prison)
        for application in Application.objects.all():
            ApplicationUserMapping.objects.get_or_create(
                user=super_admin,
                application=application,
            )


def make_test_users(clerks_per_prison=2):
    # prison clerks
    prison_clerks = []
    for prison in Prison.objects.all():
        for _ in range(clerks_per_prison):
            prison_clerks.append(create_prison_clerk(prisons=[prison]))

    # noms-ops users
    prisoner_location_admins = [create_prisoner_location_admin()]
    security_users = [
        create_security_staff_user(),
        create_security_staff_user(name_and_password='prison-security', prisons=[Prison.objects.first()]),
    ]

    # bank admin
    bank_admins = [create_bank_admin()]
    refund_bank_admins = [create_refund_bank_admin()]

    # send money shared user
    send_money_users = [create_send_money_shared_user()]

    # create test oauth applications
    make_applications()

    def link_users_with_client(users, client_id):
        for user in users:
            ApplicationUserMapping.objects.get_or_create(
                user=user,
                application=Application.objects.get(client_id=client_id)
            )

    link_users_with_client(prison_clerks, CASHBOOK_OAUTH_CLIENT_ID)
    link_users_with_client(prisoner_location_admins, NOMS_OPS_OAUTH_CLIENT_ID)
    link_users_with_client(bank_admins, BANK_ADMIN_OAUTH_CLIENT_ID)
    link_users_with_client(refund_bank_admins, BANK_ADMIN_OAUTH_CLIENT_ID)
    link_users_with_client(send_money_users, SEND_MONEY_CLIENT_ID)
    link_users_with_client(security_users, NOMS_OPS_OAUTH_CLIENT_ID)

    return (prison_clerks, prisoner_location_admins,
            bank_admins, refund_bank_admins,
            send_money_users, security_users)


def make_test_user_admins():
    # prison user admins
    prison_clerks = []
    for prison in Prison.objects.all():
        prison_clerks.append(create_user_admin(
            create_prison_clerk, prisons=[prison], name_and_password='ua')
        )

    # security staff user admins
    security_users = [
        create_user_admin(create_security_staff_user, name_and_password='security-user-admin'),
        create_user_admin(create_security_staff_user, name_and_password='prison-security-ua',
                          prisons=[Prison.objects.first()]),
    ]

    # prisoner location user admins
    prisoner_location_admins = [
        create_user_admin(create_prisoner_location_admin, name_and_password='pla-user-admin'),
    ]

    # bank admin user admins
    refund_bank_admins = [
        create_user_admin(create_refund_bank_admin, name_and_password='rba-user-admin-1'),
        create_user_admin(create_refund_bank_admin, name_and_password='rba-user-admin-2'),
    ]

    # create test oauth applications
    make_applications()

    def link_users_with_client(users, client_id):
        for user in users:
            ApplicationUserMapping.objects.get_or_create(
                user=user,
                application=Application.objects.get(client_id=client_id)
            )

    link_users_with_client(prison_clerks, CASHBOOK_OAUTH_CLIENT_ID)
    link_users_with_client(prisoner_location_admins, NOMS_OPS_OAUTH_CLIENT_ID)
    link_users_with_client(refund_bank_admins, BANK_ADMIN_OAUTH_CLIENT_ID)
    link_users_with_client(security_users, NOMS_OPS_OAUTH_CLIENT_ID)

    return prison_clerks, prisoner_location_admins, refund_bank_admins, security_users
