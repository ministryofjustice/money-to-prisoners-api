import textwrap

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command

from core.tests.utils import make_test_users, give_superusers_full_access
from prison.models import Prison
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions


class Command(BaseCommand):
    """
    Generates data for automated or user testing, creating standard users
    and (optionally) sample transactions.
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        parser.add_argument('--protect-superusers', action='store_true',
                            help='Prevents superusers from being deleted')
        parser.add_argument('--protect-transactions', action='store_true',
                            help='Prevents existing transactions from being deleted')
        parser.add_argument('--prisons', nargs='*', default=['sample'],
                            choices=['sample', 'nomis'],
                            help='Create prisions from these sets')
        parser.add_argument('--clerks-per-prison', type=int, default=2,
                            help='The number of clerks to make for the Cashbook')
        parser.add_argument('--transactions', default='random',
                            choices=['none', 'random', 'nomis'],
                            help='Create new transactions using this method')

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'prod':
            return self.handle_prod(**options)

        verbosity = options.get('verbosity', 1)
        protect_superusers = options['protect_superusers']
        protect_transactions = options['protect_transactions']
        prisons = options['prisons']
        clerks_per_prison = options['clerks_per_prison']
        transactions = options['transactions']

        print_message = self.stdout.write if verbosity else lambda m: m

        if not protect_transactions:
            print_message('Deleting all transactions')
            Transaction.objects.all().delete()

        user_set = get_user_model().objects.all()
        if protect_superusers:
            user_set = user_set.exclude(is_superuser=True)
        print_message('Deleting %d users' % user_set.count())
        user_set.delete()

        print_message('Deleting all prisons')
        Prison.objects.all().delete()

        fixtures = ['initial_groups.json']
        if 'sample' in prisons:
            fixtures.append('test_prisons.json')
        if 'nomis' in prisons:
            fixtures.append('test_nomis_prisons.json')
        print_message('Loading default user group and selected prison fixtures')
        call_command('loaddata', *fixtures, verbosity=verbosity)

        print_message('Giving super users full API access')
        give_superusers_full_access()

        print_message('Making test users')
        make_test_users(clerks_per_prison=clerks_per_prison)

        if transactions == 'random':
            print_message('Generating random prisoner locations and transactions')
            generate_transactions(transaction_batch=100)
        elif transactions == 'nomis':
            print_message('Generating test NOMIS prisoner locations and transactions')
            generate_transactions(
                transaction_batch=100,
                use_test_nomis_prisoners=True,
                only_new_transactions=True,
            )

    def handle_prod(self, **options):
        self.stderr.write(self.style.WARNING(
            'This action only does the bare minimum in the production environment'
        ))
        verbosity = options.get('verbosity', 1)
        call_command('loaddata', 'initial_groups.json', verbosity=verbosity)
