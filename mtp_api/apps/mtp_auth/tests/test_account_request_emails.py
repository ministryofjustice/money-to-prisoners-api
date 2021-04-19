import datetime
import random
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils.text import slugify
from django.utils.timezone import now, localtime
from faker import Faker
from model_mommy import mommy

from core.tests.utils import make_test_users, make_test_user_admins
from mtp_auth.management.commands.send_account_request_emails import Command
from mtp_auth.models import AccountRequest, Role
from prison.models import Prison

fake = Faker(locale='en_GB')


class AccountRequestEmailTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users()
        make_test_user_admins()

    def _make_account_request(self, role, prison, created):
        return mommy.make(
            AccountRequest,
            role=role,
            prison=prison,
            created=created,
            first_name=fake.first_name(),
            last_name=fake.last_name(),
            email=fake.safe_email(),
        )

    def test_emails_correctly_grouped(self):
        today = localtime(now()).replace(hour=0, minute=0, second=0, microsecond=0)

        def yesterday_sometime():
            return today - datetime.timedelta(seconds=random.randrange(1, 86400))

        prison_clerk_role = Role.objects.get(name='prison-clerk')
        prisons = list(Prison.objects.all())
        expected_names = {}
        for prison in prisons:

            key = 'test-%s-ua' % slugify(prison.name)
            expected_names[key] = set()
            for _ in range(3):
                # Request triggering email
                request = self._make_account_request(
                    role=prison_clerk_role,
                    prison=prison,
                    created=yesterday_sometime(),
                )
                expected_names[key].add('%s %s' % (request.first_name, request.last_name))
                # Requests *not* triggering emails
                self._make_account_request(
                    role=prison_clerk_role,
                    prison=prison,
                    created=yesterday_sometime() - datetime.timedelta(days=1),  # 2 days ago
                )
                self._make_account_request(
                    role=prison_clerk_role,
                    prison=prison,
                    created=yesterday_sometime() + datetime.timedelta(days=1),  # Today
                )

        # Account Requests for 'security' role have no prison
        security_role = Role.objects.get(name='security')
        security_request = self._make_account_request(
            role=security_role,
            prison=None,
            created=yesterday_sometime(),
        )
        expected_names['security'] = set()
        expected_names['security'].add('%s %s' % (security_request.first_name, security_request.last_name))

        with mock.patch.object(Command, 'email_admins') as method:
            call_command('send_account_request_emails')
        self.assertEqual(method.call_count, 3)
        for call in method.call_args_list:
            admins, role, names = call[0]

            if role.name == 'security':
                key = 'security'
            else:
                key = admins[0].username

            self.assertSetEqual(set(names), expected_names[key])

    def test_find_admins(self):
        command = Command()

        cases = [
            # ('test_name', 'role_name', 'prison_id', 'expected_admins')
            ('prison-clerk-prison-1', 'prison-clerk', 'IXB', ['test-prison-1-ua']),
            ('prison-clerk-prison-2', 'prison-clerk', 'INP', ['test-prison-2-ua']),
            ('security-prison-1', 'security', 'IXB', ['security-fiu-0', 'security-fiu-100', 'security-fiu-101']),
            ('security-no-prison', 'security', None, ['security-fiu-0', 'security-fiu-100', 'security-fiu-101']),
        ]
        for test_name, role_name, prison_id, expected_admins in cases:
            with self.subTest(test_name):
                prison = Prison.objects.get(nomis_id=prison_id) if prison_id else None
                role = Role.objects.get(name=role_name)

                admins = command.find_admins(role, prison)

                # Test correct admins/names
                admin_names = [admin.username for admin in admins]
                self.assertEqual(set(admin_names), set(expected_admins))

                # Tests all admins are in the Role's key Group
                for admin in admins:
                    groups = admin.groups.all()
                    self.assertIn(role.key_group, groups)
