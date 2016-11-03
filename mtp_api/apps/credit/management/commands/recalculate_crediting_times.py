import textwrap

from django.core.management import BaseCommand

from credit.models import CreditingTime


class Command(BaseCommand):
    """
    Run full re-calculation of times from receipt of a credit to it being credited
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)
        count = CreditingTime.objects.recalculate_crediting_times()
        if verbosity:
            self.stdout.write('Recalculated crediting times for %d credits' % count)
