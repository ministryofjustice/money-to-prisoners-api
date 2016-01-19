import textwrap
import types

from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.core.management.commands.testserver import Command as TestServerCommand
from django.db import connection

from core.tests.utils import give_superusers_full_access


class Command(TestServerCommand):
    """
    Extension of the Django testserver command which creates extra testing data
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *fixture_labels, **options):
        this = self
        verbosity = options.get('verbosity')

        required_fixture_labels = ['initial_groups', 'test_prisons']
        specified_fixture_labels = fixture_labels
        fixture_labels = required_fixture_labels + list(
            set(specified_fixture_labels) - set(required_fixture_labels)
        )

        create_test_db = connection.creation.create_test_db

        def extended_create_test_db(self, *args, **kwargs):
            # extends the test db creation method to load and generate testing data
            db_name = create_test_db(*args, **kwargs)
            call_command('loaddata', *fixture_labels, **{'verbosity': verbosity})
            this.load_test_data()
            this.create_super_admin()
            return db_name

        connection.creation.create_test_db = types.MethodType(
            extended_create_test_db,
            connection.creation
        )

        fixture_labels = ['test_prisons']  # because loaddata requires arguments
        super().handle(*fixture_labels, **options)

    def load_test_data(self, verbosity=1):
        call_command('load_test_data', protect_superusers=True, verbosity=verbosity)

    def create_super_admin(self):
        try:
            admin_user = User.objects.get(username='admin')
        except User.DoesNotExist:
            admin_user = User.objects.create_superuser(
                username='admin',
                email='admin@local',
                password='admin',
                first_name='Admin',
                last_name='User',
            )
        for group in Group.objects.all():
            admin_user.groups.add(group)
        give_superusers_full_access()

        self.stdout.write(self.style.SUCCESS('Model creation finished'))
