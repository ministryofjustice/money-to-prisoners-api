import datetime
import functools
import sys

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from mtp_common import nomis
from mtp_common.utils import format_currency

from credit.models import Credit, CREDIT_RESOLUTION, Log, LOG_ACTIONS
from prison.models import Prison

User = get_user_model()


class Command(BaseCommand):
    """
    Fix credits that the cashbook posted to NOMIS but failed to update the DB
    This will update the MTP DB to link credits to NOMIS transactions if a one-to-one match is found
    and no prior credits were already linked. No changes are posted to NOMIS; only used to make MTP DB consistent.
    """
    help = __doc__.strip().splitlines()[0]

    CREDITING_LEEWAY_DAYS = 5

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('prison', help='NOMIS id of prison.')
        parser.add_argument('date', help='Date on which credits were supposed to be credited.')
        parser.add_argument('owner', help='Username of person who tried to credit in Digital Cashbook.')

    def handle(self, prison, date, owner, **options):
        if not sys.stdin.isatty():
            raise CommandError('This command must be run interactively!')
        if not Prison.objects.filter(nomis_id=prison).exists():
            raise CommandError('Unknown prison')
        date = parse_date(date)
        if not date:
            raise CommandError('Date cannot be parsed, use YYYY-MM-DD')
        try:
            owner = User.objects.get_by_natural_key(owner)
        except User.DoesNotExist:
            raise CommandError('Username not found')
        self.stdout.write(f'Credits will be marked as credited by {owner.get_full_name()}')

        # find credits that are "stuck" in the cashbook
        uncredited_credits = find_uncredited_credits(prison, date)
        if not uncredited_credits:
            self.stdout.write(self.style.ERROR('No uncredited credits found'))
            return

        self.stdout.write(f'Found {len(uncredited_credits)} uncredited credits')
        for credit in uncredited_credits:  # type: Credit
            self.stdout.write(describe_mtp_credit(credit))
        self.stdout.write('\n')

        # find and link possible credits already in NOMIS
        mapped_credits = self.map_uncredited_to_nomis(date, uncredited_credits)
        if mapped_credits:
            self.stdout.write('\nDecide which credits with matching NOMIS transactions should be linked automatically:')
        for credit, transaction in mapped_credits:
            self.prompt_to_mark_credited(credit, transaction, owner)

    def map_uncredited_to_nomis(self, date, uncredited_credits):
        # a credit can only be credited from the day after it's received
        from_date = date + datetime.timedelta(days=1)
        # give leeway for credited day being some time later (e.g. after a long weekend)
        to_date = date + datetime.timedelta(days=self.CREDITING_LEEWAY_DAYS)

        mapped_credits = dict()
        for credit in uncredited_credits:  # type: Credit
            expected_transaction_description = f'Sent by {credit.sender_name}'

            transactions = find_credits_in_nomis(credit.prison_id, credit.prisoner_number, from_date, to_date)
            transactions = list(filter(
                lambda t: t['description'] == expected_transaction_description and t['amount'] == credit.amount,
                transactions
            ))
            if not transactions:
                self.stdout.write(self.style.ERROR(
                    f'Cannot find possible transactions in NOMIS for credit {credit.id} '
                    f'within {self.CREDITING_LEEWAY_DAYS} days'
                ))
                continue

            if len(transactions) > 1:
                self.stdout.write(self.style.ERROR(
                    f'Credit {credit.id} has multiple matching transactions in NOMIS! None will be linked.'
                ))
            else:
                transaction = transactions[0]
                transaction_id = transaction['id']
                if nomis_transaction_already_linked(transaction_id):
                    self.stdout.write(self.style.ERROR(
                        f'Credit {credit.id} matches a transaction in NOMIS that was linked to a previous credit! '
                        'No uncredited credits will be linked to the matching transaction.'
                    ))
                    # ensure this transaction gets linked to none of this batch of uncredited credits
                    mapped_credits[transaction_id] = None
                elif transaction_id in mapped_credits:
                    self.stdout.write(self.style.ERROR(
                        f'Credit {credit.id} matches a transaction in NOMIS that was already mapped to other credits! '
                        'None will be linked.'
                    ))
                    # ensure this transaction gets linked to no credits because it matches several
                    mapped_credits[transaction_id] = None
                else:
                    self.stdout.write(f'Credit {credit.id} has one matching transaction in NOMIS')
                    mapped_credits[transaction_id] = (credit, transaction)
            for transaction in transactions:
                self.stdout.write(describe_nomis_transaction(transaction))

        return list(mapped_credits.values())

    def prompt_to_mark_credited(self, credit: Credit, transaction: dict, owner: User):
        # mimic POST to /credits/actions/credit/
        self.stdout.write(
            '\nCredit can be linked to NOMIS transaction\n'
            f'{describe_mtp_credit(credit)}\n{describe_nomis_transaction(transaction)}'
        )
        response = input(f'Should credit {credit.id} be linked to transaction {transaction["id"]} [N/y]: ')
        if response.strip().lower() != 'y':
            return
        mark_credited(credit, transaction, owner)


def find_uncredited_credits(prison, date):
    query_list = Credit.objects.credit_pending().filter(
        prison_id=prison,
        received_at__date=date,
        resolution=CREDIT_RESOLUTION.PENDING,  # to exclude "manual" credits just in case
        nomis_transaction_id__isnull=True,
    ).order_by('pk')
    return list(query_list)


def display_id(credit_or_transaction_id):
    return str(credit_or_transaction_id).ljust(13)


def amount(pence: int):
    return format_currency(pence).rjust(8)


def describe_mtp_credit(credit: Credit):
    return f'\tMTP\t{display_id(credit.id)}\t{credit.received_at.date()}\t' \
           f'{amount(credit.amount)}\t{credit.prisoner_number}\t{credit.sender_name}'


def describe_nomis_transaction(transaction: dict):
    return f"\tNOMIS\t{display_id(transaction['id'])}\t{transaction['date']}\t" \
           f"{amount(transaction['amount'])}\t{transaction['description']}"


@functools.lru_cache(1)
def find_credits_in_nomis(prison, prisoner_number, from_date, to_date):
    # all "cash" account transactions for given date range
    transactions = nomis.get_transaction_history(
        prison, prisoner_number, 'cash',
        from_date=from_date, to_date=to_date,
    )['transactions']
    # filter only for MTDS transactions (should be used only by this service for crediting)
    transactions = filter(lambda t: t['type']['code'] == 'MTDS', transactions)
    return list(transactions)


@functools.lru_cache(1)
def nomis_transaction_already_linked(transaction_id):
    return Credit.objects.filter(nomis_transaction_id=transaction_id).exists()


def mark_credited(credit: Credit, transaction: dict, owner: User):
    # NB: must match actions performed by Credit.credit_prisoner()
    # but that method cannot be used directly because of crediting datetime manipulation

    # pretend crediting happened at midday as time-of-day is not known from NOMIS transaction
    credited_date = timezone.make_aware(parse_datetime(transaction['date'] + ' 12:00:00'))

    credit.resolution = CREDIT_RESOLUTION.CREDITED
    credit.nomis_transaction_id = transaction['id']
    credit.owner = owner
    credit.save()
    Log.objects.create(
        created=credited_date,
        modified=credited_date,
        credit=credit,
        action=LOG_ACTIONS.CREDITED,
        user=owner,
    )
