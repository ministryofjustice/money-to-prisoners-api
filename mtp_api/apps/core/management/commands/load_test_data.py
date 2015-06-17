from django.core.management.base import BaseCommand
from django.core.management import call_command
from mtp_auth.tests.mommy_recipes import create_prison_user_mapping

from prison.models import Prison


class Command(BaseCommand):

    def handle(self, *args, **options):
        call_command(
            'loaddata',
            'test_prisons.json', 'test_transactions.json'
        )
        for prison in Prison.objects.all():
            create_prison_user_mapping(prison)
