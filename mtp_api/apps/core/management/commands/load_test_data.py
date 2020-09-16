import logging
import textwrap

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command

from mtp_common.test_utils import silence_logger

from account.models import Balance
from core.tests.utils import (
    create_super_admin,
    give_superusers_full_access,
    make_test_users,
    make_test_user_admins,
)
from credit.models import Credit
from disbursement.models import Disbursement
from disbursement.tests.utils import generate_disbursements
from payment.models import Batch, Payment
from payment.tests.utils import generate_payments
from performance.tests.utils import generate_digital_takeup
from prison.models import Prison, PrisonerLocation
from prison.tests.utils import load_prisoner_locations_from_file, load_random_prisoner_locations
from security.tests.utils import generate_checks, generate_prisoner_profiles_from_prisoner_locations, generate_sender_profiles_from_prisoner_profiles
from security.models import Check, PrisonerProfile, RecipientProfile, SavedSearch, SenderProfile
from transaction.models import Transaction
from transaction.tests.utils import generate_transactions

User = get_user_model()

class Command(BaseCommand):
    """
    Generates data for automated or user testing, creating standard users
    and (optionally) sample credits.
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        parser.add_argument('--no-protect-superusers', action='store_true',
                            help='Dont prevent superusers from being deleted')
        parser.add_argument('--protect-usernames', nargs='*',
                            help='Prevents specific usernames being deleted')
        parser.add_argument('--protect-credits', action='store_true',
                            help='Prevents existing credits from being deleted')
        parser.add_argument('--prisons', nargs='*', default=['sample'],
                            choices=['sample', 'nomis', 'mtp', 'nomis-api-dev'],
                            help='Create prisons from these sets')
        parser.add_argument('--prisoners', nargs='*', default=['sample'],
                            choices=['sample', 'nomis', 'nomis-api-dev'],
                            help='Create prisoners from these sets')
        parser.add_argument('--number-of-prisoners', default=50, type=int,
                            help='Number of sample prisoners to create (no effect for nomis)')
        parser.add_argument('--number-of-senders', default=50, type=int,
                            help='Number of sample senders to create')
        parser.add_argument('--clerks-per-prison', type=int, default=2,
                            help='The number of clerks to make for the Cashbook')
        parser.add_argument('--credits', default='random',
                            choices=['none', 'random', 'nomis', 'production-scale'],
                            help='Create new credits using this method')
        parser.add_argument('--number-of-transactions', default=20, type=int,
                            help='Number of new transactions to create')
        parser.add_argument('--number-of-payments', default=200, type=int,
                            help='Number of new payments to create')
        parser.add_argument('--number-of-disbursements', default=50, type=int,
                            help='Number of new disbursements to create')
        parser.add_argument('--number-of-checks', default=10, type=int,
                            help='Number of new security checks to create')
        parser.add_argument('--digital-takeup', action='store_true',
                            help='Generate digital take-up')
        parser.add_argument('--days-of-history', default=7, type=int,
                            help='Number of days of historical credits')

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'prod':
            return self.handle_prod(**options)

        verbosity = options.get('verbosity', 1)
        no_protect_superusers = options['no_protect_superusers']
        protect_usernames = options['protect_usernames']
        protect_credits = options['protect_credits']
        prisons = options['prisons']
        prisoners = options['prisoners']
        number_of_prisoners = options['number_of_prisoners']
        number_of_senders = options['number_of_senders']
        clerks_per_prison = options['clerks_per_prison']
        credits = options['credits']
        number_of_transactions = options['number_of_transactions']
        number_of_payments = options['number_of_payments']
        number_of_disbursements = options['number_of_disbursements']
        number_of_checks = options['number_of_checks']
        days_of_history = options['days_of_history']


        print_message = self.stdout.write if verbosity else lambda m: m

        if not protect_credits and credits != 'production-scale':
            print_message('Deleting all credits')
            Balance.objects.all().delete()
            Transaction.objects.all().delete()
            Payment.objects.all().delete()
            Credit.objects_all.all().delete()
            Batch.objects.all().delete()
            SenderProfile.objects.all().delete()
            PrisonerProfile.objects.all().delete()
            SavedSearch.objects.all().delete()
            Disbursement.objects.all().delete()
            RecipientProfile.objects.all().delete()
            Check.objects.all().delete()

        if credits == 'production-scale':
            # N.B. This scenario will eat your RAM like there's no tomorrow.
            # If running it outside your development environment, be sure that it's not using the same
            # resource pool as a production service
            # If running it on your development environment you may need to tweak
            number_of_existing_transactions  = Transaction.objects.count()
            number_of_existing_payments  = Payment.objects.count()
            number_of_existing_prisoner_locations = PrisonerLocation.objects.count()
            number_of_existing_prisoners_profiles = PrisonerProfile.objects.count()
            number_of_existing_disbursements  = Disbursement.objects.count()
            number_of_existing_checks  = Check.objects.count()
            number_of_existing_senders  = SenderProfile.objects.count()

            number_of_existing_prisoners = min([number_of_existing_prisoner_locations, number_of_existing_prisoners_profiles])

            number_of_desired_transactions = 300000
            number_of_desired_payments = 3000000
            number_of_desired_prisoners = 80000
            number_of_desired_senders =  700000
            number_of_desired_disbursements = 20000
            number_of_desired_checks = 900000

            number_of_transactions = max(0, number_of_desired_transactions - number_of_existing_transactions)
            print_message(
                f'Number of transactions to be created is {number_of_desired_transactions} - {number_of_existing_transactions} <= {number_of_transactions}'
            )
            number_of_payments = max(0, number_of_desired_payments - number_of_existing_payments)
            print_message(
                f'Number of payments to be created is {number_of_desired_payments} - {number_of_existing_payments} <= {number_of_payments}'
            )
            number_of_prisoners = max(0, number_of_desired_prisoners - number_of_existing_prisoners)
            print_message(
                f'Number of prisoners to be created is {number_of_desired_prisoners} - {number_of_existing_prisoners} <= {number_of_prisoners}'
            )
            number_of_senders = max(0, number_of_desired_senders - number_of_existing_senders)
            print_message(
                f'Number of senders to be created is {number_of_desired_senders} - {number_of_existing_senders} <= {number_of_senders}'
            )
            number_of_disbursements = max(0, number_of_desired_disbursements - number_of_existing_disbursements)
            print_message(
                f'Number of disbursements to be created is {number_of_desired_disbursements} - {number_of_existing_disbursements} <= {number_of_disbursements}'
            )
            number_of_checks = max(0, number_of_desired_checks - number_of_existing_checks)
            print_message(
                f'Number of checks to be created is {number_of_desired_checks} - {number_of_existing_checks} <= {number_of_checks}'
            )
            days_of_history = 1300
            prisons.append('nomis-api-dev')
            prisoners.append('sample')
        else:
            user_set = get_user_model().objects.exclude(username__in=protect_usernames or [])
            if not no_protect_superusers:
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
        if 'nomis-api-dev' in prisons:
            fixtures.append('dev_nomis_api_prisons.json')
        print_message('Loading default user group and selected prison fixtures')
        call_command('loaddata', *fixtures, verbosity=verbosity)

        print_message('Giving super users full API access')
        create_super_admin(self.stdout, self.style.SUCCESS)
        give_superusers_full_access()

        if credits != 'production-scale' or User.objects.count() < 2:
            print_message('Making test users')
            make_test_users(clerks_per_prison=clerks_per_prison)
            print_message('Making test user admins')
            make_test_user_admins()
            print_message('Making token retrieval user')

        prisoner_locations = None
        if 'nomis' in prisoners:
            prisoner_locations = load_prisoner_locations_from_file('test_nomis_prisoner_locations.csv')
        if 'nomis-api-dev' in prisoners:
            prisoner_locations = load_prisoner_locations_from_file('dev_nomis_api_prisoner_locations.csv')
        if 'sample' in prisoners:
            prisoner_locations = load_random_prisoner_locations(number_of_prisoners=number_of_prisoners)
        if not prisoner_locations:
            prisoner_locations = PrisonerLocation.objects.all()

        print_message(f'Generating (at least) {number_of_prisoners} prisoner profiles')
        prisoner_profiles = generate_prisoner_profiles_from_prisoner_locations(prisoner_locations)
        print_message(f'Generated {len(prisoner_profiles)} prisoner profiles')
        print_message(f'Generating {number_of_senders} sender profiles')
        sender_profiles = generate_sender_profiles_from_prisoner_profiles(number_of_senders)
        print_message(f'Generated {len(sender_profiles)} sender profiles')

        if credits == 'random':
            print_message('Generating random credits')
            generate_transactions(transaction_batch=number_of_transactions)
            generate_payments(payment_batch=number_of_payments)
        elif credits == 'nomis':
            print_message('Generating test NOMIS credits')
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
        elif credits == 'production-scale':
            print_message('Generating production-like transactions')
            generate_transactions(
                transaction_batch=number_of_transactions,
                predetermined_transactions=True,
                consistent_history=True,
                include_debits=True,
                include_administrative_credits=True,
                include_unidentified_credits=True,
                days_of_history=days_of_history
            )
            print_message('Generating production-like payments/credits')
            generate_payments(
                payment_batch=number_of_payments,
                consistent_history=True,
                days_of_history=days_of_history,
                attach_profiles_to_individual_credits=False
            )
        print_message('Generating disbursements')
        generate_disbursements(
            disbursement_batch=number_of_disbursements,
            days_of_history=days_of_history
        )
        print_message('Generating checks')
        generate_checks(
            number_of_checks=number_of_checks
        )
        print_message('Associating credits with profiles')
        with silence_logger(level=logging.WARNING):
            call_command('update_security_profiles')

        digital_takeup = options['digital_takeup']
        if digital_takeup:
            print_message('Generating digital take-up')
            generate_digital_takeup(days_of_history=days_of_history)

    def handle_prod(self, **options):
        self.stderr.write(self.style.WARNING(
            'This action only does the bare minimum in the production environment'
        ))
        verbosity = options.get('verbosity', 1)
        call_command('loaddata', 'initial_groups.json', verbosity=verbosity)
