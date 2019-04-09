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
from mtp_auth.models import AccountRequest, Role
from prison.models import Prison

fake = Faker(locale='en_GB')


class AccountRequestEmailTestCase(TestCase):
    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        make_test_users()
        make_test_user_admins()

    def test_emails_correctly_grouped(self):
        from mtp_auth.management.commands.send_account_request_emails import Command

        today = localtime(now()).replace(hour=0, minute=0, second=0, microsecond=0)

        def yesterday_sometime():
            return today - datetime.timedelta(seconds=random.randrange(1, 86400))

        role = Role.objects.get(name='prison-clerk')
        prisons = list(Prison.objects.all())
        expected_names = {}
        for prison in prisons:
            expected_names[prison] = set()
            for _ in range(3):
                request = mommy.make(
                    AccountRequest, created=yesterday_sometime(),
                    prison=prison, role=role,
                    first_name=fake.first_name(), last_name=fake.last_name(), email=fake.safe_email()
                )
                expected_names[prison].add('%s %s' % (request.first_name, request.last_name))
                mommy.make(
                    AccountRequest, created=yesterday_sometime() - datetime.timedelta(days=1),
                    prison=prison, role=role,
                    first_name=fake.first_name(), last_name=fake.last_name(), email=fake.safe_email()
                )
                mommy.make(
                    AccountRequest, created=yesterday_sometime() + datetime.timedelta(days=1),
                    prison=prison, role=role,
                    first_name=fake.first_name(), last_name=fake.last_name(), email=fake.safe_email()
                )

        with mock.patch.object(Command, 'email_admins') as method:
            call_command('send_account_request_emails')
        self.assertEqual(method.call_count, 2)
        for call in method.call_args_list:
            admins, role, prison, names = call[0]
            self.assertTrue(all(
                (
                    admin.groups.filter(pk=role.key_group_id).exists() and
                    admin.prisonusermapping.prisons.filter(pk=prison.pk).exists()
                )
                for admin in admins
            ))
            self.assertEqual(set(admin.username for admin in admins), {'test-%s-ua' % slugify(prison.name)})
            self.assertSetEqual(set(names), expected_names[prison])
