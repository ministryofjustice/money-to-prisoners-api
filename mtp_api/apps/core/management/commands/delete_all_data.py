import textwrap

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError

from account.models import Batch
from prison.models import Prison, PrisonerLocation
from transaction.models import Transaction


class Command(BaseCommand):
    """
    Deletes all data, optionally protecting certain subsets.
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        parser.add_argument('--protect-users', default='none',
                            choices=['all', 'superusers', 'none'],
                            help='Prevents users from being deleted')
        parser.add_argument('--protect-prisons', action='store_true',
                            help='Prevents prisons from being deleted')
        parser.add_argument('--protect-prisoner-locations', action='store_true',
                            help='Prevents prisoner locations from being deleted')
        parser.add_argument('--protect-transactions', action='store_true',
                            help='Prevents existing transactions from being deleted')

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'prod':
            raise CommandError('This action is not permitted in the production environment')

        verbosity = options['verbosity']
        protect_users = options['protect_users']
        protect_prisons = options['protect_prisons']
        protect_prisoner_locations = options['protect_prisoner_locations']
        protect_transactions = options['protect_transactions']

        print_message = self.stdout.write if verbosity else lambda m: m

        if not protect_transactions:
            print_message('Deleting all transactions')
            Batch.objects.all().delete()
            Transaction.objects.all().delete()

        if not protect_prisoner_locations:
            print_message('Deleting all prisoner locations')
            PrisonerLocation.objects.all().delete()

        if protect_users != 'all':
            user_set = get_user_model().objects.all()
            if protect_users == 'superusers':
                user_set = user_set.exclude(is_superuser=True)
            print_message('Deleting %d users' % user_set.count())
            user_set.delete()

        if not protect_prisons:
            print_message('Deleting all prisons')
            Prison.objects.all().delete()
