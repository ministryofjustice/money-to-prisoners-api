from datetime import timedelta
import textwrap

from django.core.management import BaseCommand, CommandError
from django.utils.timezone import now

from credit.models import Credit
from payment.models import Payment


class Command(BaseCommand):
    """
    Delete payments that are still pending after at least a day.
    These are abandoned payments that never succeeded to pass through GOV.UK Pay.
    """
    help = textwrap.dedent(__doc__).strip()

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--age', type=int, default=7, help='The minimum age of the payment in days')

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)
        age = options['age']
        if age < 1:
            raise CommandError('Payment age must be at least 1 day')
        abandoned_payments = Payment.objects.abandoned(now() - timedelta(days=age)).values('pk')
        abandoned_count = len(abandoned_payments)
        if not abandoned_count:
            if verbosity > 1:
                self.stdout.write('No abandoned credits older than %d day(s)' % age)
            return
        if verbosity > 1:
            abandoned_payment_ids = map(lambda payment: str(payment['pk']), abandoned_payments)
            self.stdout.write('Deleting abandoned payments older than %d day(s): %s' %
                              (age, ','.join(abandoned_payment_ids)))
        elif verbosity:
            self.stdout.write('Deleting %d abandoned payment(s) older than %d day(s)' % (abandoned_count, age))

        _, deleted_details = Credit.objects_all.filter(payment__in=abandoned_payments).delete()
        if not (deleted_details[Credit._meta.label] == deleted_details[Payment._meta.label] == abandoned_count):
            raise CommandError('Unexpected number of abandoned payments/credits were deleted')
