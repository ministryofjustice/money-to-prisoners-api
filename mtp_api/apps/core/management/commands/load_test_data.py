import textwrap

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command

from account.models import Balance
from core.tests.utils import (
    make_test_users, make_test_user_admins, give_superusers_full_access
)
from credit.models import Credit
from payment.models import Batch, Payment
from payment.tests.utils import generate_payments
from prison.models import Prison
from prison.tests.utils import load_nomis_prisoner_locations, load_random_prisoner_locations
from security.models import SenderProfile, PrisonerProfile, SecurityDataUpdate
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions


class Command(BaseCommand):
    """
    Generates data for automated or user testing, creating standard users
    and (optionally) sample credits.
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        parser.add_argument('--protect-superusers', action='store_true',
                            help='Prevents superusers from being deleted')
        parser.add_argument('--protect-usernames', nargs='*',
                            help='Prevents specific usernames being deleted')
        parser.add_argument('--protect-credits', action='store_true',
                            help='Prevents existing credits from being deleted')
        parser.add_argument('--prisons', nargs='*', default=['sample'],
                            choices=['sample', 'nomis', 'mtp'],
                            help='Create prisons from these sets')
        parser.add_argument('--prisoners', nargs='*', default=['sample'],
                            choices=['sample', 'nomis'],
                            help='Create prisoners from these sets')
        parser.add_argument('--number-of-prisoners', default=50, type=int,
                            help='Number of sample prisoners to create (no effect for nomis)')
        parser.add_argument('--clerks-per-prison', type=int, default=2,
                            help='The number of clerks to make for the Cashbook')
        parser.add_argument('--credits', default='random',
                            choices=['none', 'random', 'nomis'],
                            help='Create new credits using this method')
        parser.add_argument('--number-of-transactions', default=100, type=int,
                            help='Number of new transactions to create')
        parser.add_argument('--number-of-payments', default=100, type=int,
                            help='Number of new payments to create')
        parser.add_argument('--days-of-history', default=7, type=int,
                            help='Number of days of historical credits')

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'prod':
            return self.handle_prod(**options)

        verbosity = options.get('verbosity', 1)
        protect_superusers = options['protect_superusers']
        protect_usernames = options['protect_usernames']
        protect_credits = options['protect_credits']
        prisons = options['prisons']
        prisoners = options['prisoners']
        number_of_prisoners = options['number_of_prisoners']
        clerks_per_prison = options['clerks_per_prison']
        credits = options['credits']

        print_message = self.stdout.write if verbosity else lambda m: m

        if not protect_credits:
            print_message('Deleting all credits')
            Balance.objects.all().delete()
            Transaction.objects.all().delete()
            Payment.objects.all().delete()
            Credit.objects_all.all().delete()
            Batch.objects.all().delete()
            SenderProfile.objects.all().delete()
            PrisonerProfile.objects.all().delete()
            SecurityDataUpdate.objects.all().delete()

        user_set = get_user_model().objects.exclude(username__in=protect_usernames or [])
        if protect_superusers:
            user_set = user_set.exclude(is_superuser=True)
        print_message('Deleting %d users' % user_set.count())
        user_set.delete()

        print_message('Deleting all prisons')
        Prison.objects.all().delete()

        fixtures = ['initial_groups.json', 'initial_types.json']
        if 'sample' in prisons:
            fixtures.append('test_prisons.json')
        if 'nomis' in prisons:
            fixtures.append('test_nomis_prisons.json')
        if 'mtp' in prisons:
            fixtures.append('test_nomis_mtp_prisons.json')
        print_message('Loading default user group and selected prison fixtures')
        call_command('loaddata', *fixtures, verbosity=verbosity)

        print_message('Giving super users full API access')
        give_superusers_full_access()

        print_message('Making test users')
        make_test_users(clerks_per_prison=clerks_per_prison)
        print_message('Making test user admins')
        make_test_user_admins()

        if 'nomis' in prisoners:
            load_nomis_prisoner_locations()
        if 'sample' in prisoners:
            load_random_prisoner_locations(number_of_prisoners=number_of_prisoners)

        number_of_transactions = options['number_of_transactions']
        number_of_payments = options['number_of_payments']
        days_of_history = options['days_of_history']
        if credits == 'random':
            print_message('Generating pre-defined prisoner locations')
            print_message('Generating random prisoner locations and credits')
            generate_transactions(transaction_batch=number_of_transactions)
            generate_payments(payment_batch=number_of_payments)
        elif credits == 'nomis':
            print_message('Generating test NOMIS prisoner locations and credits')
            generate_transactions(
                transaction_batch=number_of_transactions,
                predetermined_transactions=True,
                consistent_history=True,
                include_debits=False,
                include_administrative_credits=False,
                include_unidentified_credits=True,
                days_of_history=days_of_history
            )
            generate_payments(
                payment_batch=number_of_payments,
                consistent_history=True,
                days_of_history=days_of_history
            )
        call_command('update_security_profiles')

    def handle_prod(self, **options):
        self.stderr.write(self.style.WARNING(
            'This action only does the bare minimum in the production environment'
        ))
        verbosity = options.get('verbosity', 1)
        call_command('loaddata', 'initial_groups.json', verbosity=verbosity)
