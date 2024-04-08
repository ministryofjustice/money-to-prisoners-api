import datetime

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils.timezone import make_aware
from oauth2_provider.models import Application

from core.tests.utils import make_test_users, make_test_user_admins, create_super_admin
from mtp_auth.management.commands.disable_inactive_users import User


class DisableInactiveUsersTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        self.users = make_test_users()

    def assertInactiveUsernames(self, usernames: list[str]):  # noqa: N802
        self.assertSequenceEqual(
            User.objects.filter(is_active=False).order_by('username').values_list('username', flat=True),
            sorted(usernames),
        )

    def test_users_who_have_not_logged_in_for_a_while_are_disabled(self):
        prison_clerk = self.users['prison_clerks'][0]
        bank_admin = self.users['bank_admins'][0]
        security_staff = self.users['security_staff'][0]

        date_joined = make_aware(datetime.datetime(2023, 2, 8, 12))
        last_login = make_aware(datetime.datetime(2023, 4, 10, 11))

        def set_old_last_login(user):
            user.date_joined = date_joined
            user.last_login = last_login
            user.save()

        set_old_last_login(prison_clerk)
        set_old_last_login(bank_admin)
        set_old_last_login(security_staff)

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertInactiveUsernames([prison_clerk.username, bank_admin.username, security_staff.username])

    def test_users_who_have_never_logged_in_are_disabled(self):
        prison_clerk = self.users['prison_clerks'][0]
        refund_bank_admin = self.users['refund_bank_admins'][0]
        fiu_user = self.users['security_fiu_users'][0]

        date_joined = make_aware(datetime.datetime(2023, 2, 8, 12))

        def set_unused_old_account(user):
            user.date_joined = date_joined
            user.last_login = None
            user.save()

        set_unused_old_account(prison_clerk)
        set_unused_old_account(refund_bank_admin)
        set_unused_old_account(fiu_user)

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertInactiveUsernames([prison_clerk.username, refund_bank_admin.username, fiu_user.username])

    def test_already_inactive_users_are_ignored(self):
        prison_clerk = self.users['prison_clerks'][1]
        disbursement_bank_admin = self.users['disbursement_bank_admins'][0]
        prisoner_location_admin = self.users['prisoner_location_admins'][0]

        date_joined = make_aware(datetime.datetime(2023, 2, 8, 12))
        last_login = make_aware(datetime.datetime(2023, 4, 10, 11))

        def set_already_inactive(user):
            user.date_joined = date_joined
            user.last_login = last_login
            user.is_active = False
            user.save()

        set_already_inactive(prison_clerk)
        set_already_inactive(disbursement_bank_admin)
        set_already_inactive(prisoner_location_admin)

        self.assertInactiveUsernames(
            [prison_clerk.username, disbursement_bank_admin.username, prisoner_location_admin.username],
        )
        call_command('disable_inactive_users', verbosity=0)
        self.assertInactiveUsernames(
            [prison_clerk.username, disbursement_bank_admin.username, prisoner_location_admin.username],
        )

    def test_inactive_superusers_are_ignored(self):
        create_super_admin()

        date_joined = make_aware(datetime.datetime(2023, 2, 8, 12))
        last_login = make_aware(datetime.datetime(2023, 4, 10, 11))

        def set_old_last_login(user):
            user.date_joined = date_joined
            user.last_login = last_login
            user.save()

        set_old_last_login(User.objects.get(username='admin'))

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertFalse(User.objects.filter(is_active=False).exists())

    def test_inactive_staff_are_ignored(self):
        user_admins = make_test_user_admins()
        fiu_admin = user_admins['security_fiu_uas'][0]

        date_joined = make_aware(datetime.datetime(2023, 2, 8, 12))
        last_login = make_aware(datetime.datetime(2023, 4, 10, 11))

        def set_old_last_login(user):
            user.date_joined = date_joined
            user.last_login = last_login
            user.is_staff = True  # upgrade user to allow access to django admin
            user.save()

        set_old_last_login(fiu_admin)

        call_command('disable_inactive_users', verbosity=0)
        self.assertFalse(User.objects.filter(is_active=False).exists())

    def test_inactive_users_of_other_apps_are_ignored(self):
        send_money_user = self.users['send_money_users'][0]

        date_joined = make_aware(datetime.datetime(2023, 2, 8, 12))
        last_login = make_aware(datetime.datetime(2023, 4, 10, 11))

        def set_old_last_login(user):
            user.date_joined = date_joined
            user.last_login = last_login
            user.save()

        set_old_last_login(send_money_user)

        self.assertFalse(User.objects.filter(is_active=False).exists())
        call_command('disable_inactive_users', verbosity=0)
        self.assertFalse(User.objects.filter(is_active=False).exists())

    def test_error_if_missing_applications(self):
        User.objects.all().delete()
        Application.objects.all().delete()

        with self.assertRaises(CommandError):
            call_command('disable_inactive_users', verbosity=0)
        self.assertFalse(User.objects.filter(is_active=False).exists())
