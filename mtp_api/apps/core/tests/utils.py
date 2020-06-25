from datetime import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from oauth2_provider.models import Application
from rest_framework.fields import DateField, DateTimeField

from mtp_auth.constants import (
    CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, SEND_MONEY_CLIENT_ID
)
from mtp_auth.models import Role, ApplicationUserMapping, PrisonUserMapping
from mtp_auth.tests.mommy_recipes import (
    create_bank_admin,
    create_basic_user,
    create_disbursement_bank_admin,
    create_prison_clerk,
    create_prisoner_location_admin,
    create_refund_bank_admin,
    create_security_fiu_user,
    create_security_staff_user,
    create_send_money_shared_user,
    create_user_admin,
)
from prison.models import Prison

User = get_user_model()


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
        app = Application.objects.filter(
            client_id=client_id
        ).first()
        if not app:
            app = Application.objects.create(
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
                application=app,
                key_group=key_group,
                login_url='http://localhost/%s/' % client_id,
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
        {'name': 'disbursement-admin', 'groups': ['DisbursementBankAdmin']},
    )
    make_application_and_roles(
        SEND_MONEY_CLIENT_ID, 'Send money to someone in prison',
    )


def give_superusers_full_access():
    super_admins = get_user_model().objects.filter(is_superuser=True)
    for super_admin in super_admins:
        super_admin.flags.get_or_create(name='hmpps-employee')
        PrisonUserMapping.objects.assign_prisons_to_user(super_admin, Prison.objects.all())
        for application in Application.objects.all():
            ApplicationUserMapping.objects.get_or_create(
                user=super_admin,
                application=application,
            )


def make_test_users(clerks_per_prison=2, num_security_fiu_users=1):
    # prison clerks
    prison_clerks = []
    for prison in Prison.objects.all():
        for _ in range(clerks_per_prison):
            prison_clerks.append(create_prison_clerk(prisons=[prison]))

    # noms-ops users
    prisoner_location_admins = [create_prisoner_location_admin()]
    security_fiu_users = [
        create_security_fiu_user(name_and_password=f'security-fiu-{number}')
        for number in range(num_security_fiu_users)
    ]
    security_users = [
        create_security_staff_user(),
        create_security_staff_user(name_and_password='prison-security', prisons=[Prison.objects.first()]),
        *security_fiu_users,
    ]

    # bank admin
    bank_admins = [create_bank_admin()]
    refund_bank_admins = [create_refund_bank_admin()]
    disbursement_bank_admins = [create_disbursement_bank_admin()]

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
    link_users_with_client(disbursement_bank_admins, BANK_ADMIN_OAUTH_CLIENT_ID)
    link_users_with_client(send_money_users, SEND_MONEY_CLIENT_ID)
    link_users_with_client(security_users, NOMS_OPS_OAUTH_CLIENT_ID)

    return {
        'prison_clerks': prison_clerks,
        'prisoner_location_admins': prisoner_location_admins,
        'bank_admins': bank_admins,
        'refund_bank_admins': refund_bank_admins,
        'disbursement_bank_admins': disbursement_bank_admins,
        'send_money_users': send_money_users,
        'security_staff': security_users,
        'security_fiu_users': security_fiu_users,
    }


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

    return {
        'prison_clerk_uas': prison_clerks,
        'prisoner_location_uas': prisoner_location_admins,
        'bank_admin_uas': refund_bank_admins,
        'security_staff_uas': security_users
    }


# TODO: Remove once all apps move to NOMIS Elite2
def make_token_retrieval_user():
    user = create_basic_user('_token_retrieval')
    user.user_permissions.add(
        Permission.objects.get_by_natural_key('view_token', 'core', 'token')
    )
    for application in Application.objects.all():
        ApplicationUserMapping.objects.get_or_create(
            user=user,
            application=application,
        )
    return user


def format_date_or_datetime(value):
    """
    Formats a date or datetime using DRF fields.

    This is for use in tests when comparing dates and datetimes with JSON-formatted values.
    """
    if not value:
        return value

    if isinstance(value, datetime):
        return DateTimeField().to_representation(value)
    return DateField().to_representation(value)


def create_super_admin(stdout=None, style_success=None):
    try:
        admin_user = User.objects.get(username='admin')
    except User.DoesNotExist:
        admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@mtp.local',
            password='adminadmin',
            first_name='Admin',
            last_name='User',
        )
    for group in Group.objects.all():
        admin_user.groups.add(group)

    if stdout and style_success:
        stdout.write(style_success('Model creation finished'))


def delete_non_related_nullable_fields(queryset, null_fields_to_leave_populated=None):
    """
    This is intended for testing the minimum amount of data needed to be populated on an
    object for a codeflow, whilst also using the test data setup fixtures of the happy path
    """
    blankable_fields = set()
    sample_instance = queryset.first()
    for field in sample_instance._meta.get_fields():
        # We don't want to blank any related objects
        if (
            getattr(field, 'null', False)
            and not getattr(field, 'related_model', False)
        ):
            blankable_fields.add(field.name)
    if null_fields_to_leave_populated:
        to_be_blanked_fields = blankable_fields - null_fields_to_leave_populated
    else:
        to_be_blanked_fields = blankable_fields

    for instance in queryset:
        for field in to_be_blanked_fields:
            setattr(instance, field, None)
        instance.save()
        instance.refresh_from_db()
        assert all([
            getattr(instance, field_name) is None
            for field_name in to_be_blanked_fields
        ])
