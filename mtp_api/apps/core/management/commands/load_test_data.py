from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth.models import User

from core.tests.utils import make_test_users, \
    make_test_oauth_applications


class Command(BaseCommand):

    def handle(self, *args, **options):
        call_command(
            'loaddata',
            'test_prisons.json',
            'test_transactions.json',
            'initial_groups.json'
        )

        User.objects.all().delete()
        make_test_users()

        make_test_oauth_applications()
