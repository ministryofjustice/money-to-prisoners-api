import textwrap

from django.core.management import BaseCommand

from performance.prediction import train_digital_takeup


class Command(BaseCommand):
    """
    Train prediction curve parameters using stored data
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        train_digital_takeup()
