import datetime
import textwrap

from django.core.management import BaseCommand
from django.utils import timezone

from account.models import Balance
from credit.models import Credit
from disbursement.models import Disbursement
from notification.models import Event
from payment.models import Batch, Payment
from prison.models import Prison, PrisonerLocation
from security.models import (
    RecipientProfile, SenderProfile, PrisonerProfile, SavedSearch
)
from transaction.models import Transaction


class Command(BaseCommand):
    """
    Deletes data which is older than 7 years
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        verbosity = options['verbosity']

        print_message = self.stdout.write if verbosity else lambda m: m

        today = timezone.localdate()
        seven_years_ago = today - datetime.timedelta(days=7*365)

        print_message(f'\nDeleting Credits older than {seven_years_ago}...')
        records_deleted = Credit.objects.filter(created__lt=seven_years_ago).delete()
        print_message(f'Records deleted: {records_deleted}.')

        print_message(f'\nDeleting Disbursments older than {seven_years_ago}...')
        records_deleted = Disbursement.objects.filter(created__lt=seven_years_ago).delete()
        print_message(f'Records deleted: {records_deleted}.')

        print_message(f'\nDeleting Transactions older than {seven_years_ago}...')
        records_deleted = Transaction.objects.filter(received_at__lt=seven_years_ago).delete()
        print_message(f'Records deleted: {records_deleted}.')

        # TODO: It this unnecessary? Old Payments would be linked to old Credits
        #       They'd be deleted by this point.
        #       Are there any old Payments potentially not linked to old Credits?
        print_message(f'\nDeleting Payment older than {seven_years_ago}...')
        records_deleted = Payment.objects.filter(modified__lt=seven_years_ago).delete()
        print_message(f'Records deleted: {records_deleted}.')
