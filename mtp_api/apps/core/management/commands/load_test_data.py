import textwrap

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command

from account.models import Batch, Balance
from core.tests.utils import (
    make_test_users, make_test_user_admins, give_superusers_full_access
)
from prison.models import Prison
from prison.tests.utils import generate_predefined_prisoner_locations
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
        parser.add_argument('--protect-usernames', nargs='*',
                            help='Prevents specific usernames being deleted')
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
        parser.add_argument('--number-of-transactions', default=200, type=int,
                            help='Number of new transactions to create')

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'prod':
            return self.handle_prod(**options)

        verbosity = options.get('verbosity', 1)
        protect_superusers = options['protect_superusers']
        protect_usernames = options['protect_usernames']
        protect_transactions = options['protect_transactions']
        prisons = options['prisons']
        clerks_per_prison = options['clerks_per_prison']
        transactions = options['transactions']

        print_message = self.stdout.write if verbosity else lambda m: m

        if not protect_transactions:
            print_message('Deleting all transactions')
            Balance.objects.all().delete()
            Batch.objects.all().delete()
            Transaction.objects.all().delete()

        user_set = get_user_model().objects.exclude(username__in=protect_usernames or [])
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
        print_message('Making test user admins')
        make_test_user_admins()

        number_of_transactions = options['number_of_transactions']
        if transactions == 'random':
            print_message('Generating pre-defined prisoner locations')
            # to allow for automated testing
            generate_predefined_prisoner_locations()
            print_message('Generating random prisoner locations and transactions')
            generate_transactions(transaction_batch=number_of_transactions)
        elif transactions == 'nomis':
            print_message('Generating test NOMIS prisoner locations and transactions')
            generate_transactions(
                transaction_batch=number_of_transactions,
                use_test_nomis_prisoners=True,
                predetermined_transactions=True,
                only_new_transactions=True,
                consistent_history=True,
                include_debits=False,
                include_administrative_credits=False,
                include_unidentified_credits=False,
                include_online_payments=False
            )

    def handle_prod(self, **options):
        self.stderr.write(self.style.WARNING(
            'This action only does the bare minimum in the production environment'
        ))
        verbosity = options.get('verbosity', 1)
        call_command('loaddata', 'initial_groups.json', verbosity=verbosity)
