import datetime

from dateutil.relativedelta import relativedelta
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils.timezone import make_aware, now
from oauth2_provider.models import Application

from core.tests.utils import make_test_users, make_test_user_admins, create_super_admin
from mtp_auth.management.commands.disable_inactive_users import User


class DisableInactiveUsersTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    date_joined = make_aware(datetime.datetime(2023, 2, 8, 12))
    last_login = make_aware(datetime.datetime(2023, 4, 10, 11))

    def setUp(self):
        super().setUp()
        self.users = make_test_users()
        self.user_admins = make_test_user_admins()

    def assertInactiveUsernames(self, *usernames):  # noqa: N802
        self.assertSequenceEqual(
            User.objects.filter(is_active=False).order_by('username').values_list('username', flat=True),
            sorted(usernames),
        )

    def make_user_old(self, user, /, **kwargs):
        user.date_joined = self.date_joined
        user.last_login = self.last_login
        for attr, value in kwargs.items():
            setattr(user, attr, value)
        user.save()

    def test_users_who_have_not_logged_in_for_a_while_are_disabled(self):
        prison_clerk = self.users['prison_clerks'][0]
        prison_clerk_user_admin = self.user_admins['prison_clerk_uas'][0]
        bank_admin = self.users['bank_admins'][0]
        security_staff = self.users['security_staff'][0]

        self.make_user_old(prison_clerk)
        self.make_user_old(prison_clerk_user_admin)
        self.make_user_old(bank_admin)
        self.make_user_old(security_staff)

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertInactiveUsernames(
            prison_clerk.username,
            prison_clerk_user_admin.username,
            bank_admin.username,
            security_staff.username,
        )

    def test_users_who_have_never_logged_in_are_disabled(self):
        prison_clerk = self.users['prison_clerks'][0]
        refund_bank_admin = self.users['refund_bank_admins'][0]
        bank_admin_user_admin = self.user_admins['bank_admin_uas'][0]
        fiu_user = self.users['security_fiu_users'][0]

        self.make_user_old(prison_clerk, last_login=None)
        self.make_user_old(refund_bank_admin, last_login=None)
        self.make_user_old(bank_admin_user_admin, last_login=None)
        self.make_user_old(fiu_user, last_login=None)

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertInactiveUsernames(
            prison_clerk.username,
            refund_bank_admin.username,
            bank_admin_user_admin.username,
            fiu_user.username,
        )

    def test_user_admins_are_given_longer_to_become_inactive(self):
        prison_clerk_user_admin = self.user_admins['prison_clerk_uas'][0]  # user admin
        bank_admin_user_admin = self.user_admins['bank_admin_uas'][0]  # user admin
        security_staff = self.users['security_staff'][0]  # not a user admin

        # old enough for a normal user to be deactivated, but not user admins
        date_joined = now() - relativedelta(months=5)
        last_login = now() - relativedelta(months=4)

        self.make_user_old(prison_clerk_user_admin, date_joined=date_joined, last_login=last_login)
        self.make_user_old(bank_admin_user_admin, date_joined=date_joined, last_login=None)
        self.make_user_old(security_staff, date_joined=date_joined, last_login=last_login)

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertInactiveUsernames(security_staff.username)

    def test_already_inactive_users_are_ignored(self):
        prison_clerk = self.users['prison_clerks'][1]
        disbursement_bank_admin = self.users['disbursement_bank_admins'][0]
        prisoner_location_admin = self.users['prisoner_location_admins'][0]
        prisoner_location_user_admin = self.user_admins['prisoner_location_uas'][0]

        self.make_user_old(prison_clerk, is_active=False)
        self.make_user_old(disbursement_bank_admin, is_active=False)
        self.make_user_old(prisoner_location_admin, is_active=False)
        self.make_user_old(prisoner_location_user_admin, is_active=False)

        self.assertInactiveUsernames(
            prison_clerk.username,
            disbursement_bank_admin.username,
            prisoner_location_admin.username,
            prisoner_location_user_admin.username,
        )
        call_command('disable_inactive_users', verbosity=0)
        self.assertInactiveUsernames(
            prison_clerk.username,
            disbursement_bank_admin.username,
            prisoner_location_admin.username,
            prisoner_location_user_admin.username,
        )

    def test_inactive_superusers_are_ignored(self):
        create_super_admin()

        self.make_user_old(User.objects.get(username='admin'))

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertFalse(User.objects.filter(is_active=False).exists())

    def test_inactive_staff_are_ignored(self):
        fiu_admin = self.user_admins['security_fiu_uas'][0]

        # upgrade user to allow access to django admin
        self.make_user_old(fiu_admin, is_staff=True)

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertFalse(User.objects.filter(is_active=False).exists())

    def test_inactive_users_of_other_apps_are_ignored(self):
        send_money_user = self.users['send_money_users'][0]

        self.make_user_old(send_money_user)

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertFalse(User.objects.filter(is_active=False).exists())

    def test_error_if_missing_applications(self):
        User.objects.all().delete()
        Application.objects.all().delete()

        self.assertFalse(User.objects.filter(is_active=False).exists())
        with self.assertRaises(CommandError):
            call_command('disable_inactive_users', verbosity=0)
        self.assertFalse(User.objects.filter(is_active=False).exists())
