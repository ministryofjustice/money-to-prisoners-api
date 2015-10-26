import textwrap

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command
from oauth2_provider.models import Application

from core.tests.utils import make_test_users
from prison.models import Prison
from mtp_auth.models import ApplicationUserMapping, PrisonUserMapping
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions


class Command(BaseCommand):
    """
    Generates data for automated testing, creating standard users
    and (optionally) random transactions.
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        parser.add_argument('--protect-superusers', action='store_true',
                            help='Prevents superusers from being deleted')
        parser.add_argument('--protect-transactions', action='store_true',
                            help='Prevents existing transactions from being deleted')
        parser.add_argument('--generate-transactions', default='random',
                            choices=['none', 'random'],
                            help='Create new transactions using this method')

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'prod':
            return self.handle_prod(**options)

        protect_superusers = options.get('protect_superusers')
        protect_transactions = options.get('protect_transactions')
        generate_method = options.get('generate_transactions')

        if not protect_transactions:
            self.stdout.write('Deleting all transactions')
            Transaction.objects.all().delete()

        user_set = get_user_model().objects.all()
        if protect_superusers:
            user_set = user_set.exclude(is_superuser=True)
        self.stdout.write('Deleting %d users' % user_set.count())
        user_set.delete()

        self.stdout.write('Deleting all prisons')
        Prison.objects.all().delete()

        self.stdout.write('Loading default prison and user group fixtures')
        call_command(
            'loaddata',
            'test_prisons.json',
            'initial_groups.json',
        )

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

        self.stdout.write('Making test users')
        make_test_users()

        if generate_method != 'none':
            self.stdout.write('Generating random transactions')
            generate_transactions(transaction_batch=100)

    def handle_prod(self, **options):
        self.stderr.write(self.style.WARNING(
            'This action only does the bare minimum in the production environment'
        ))
        call_command('loaddata', 'initial_groups.json')
