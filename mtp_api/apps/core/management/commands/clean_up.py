import textwrap

from django.conf import settings
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    """
    Perform periodic clean-up removing expired DB models.
    This is designed to run on only one instance in an auto-
    scaling group.
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)

        if settings.RUN_CLEANUP_TASKS:
            if verbosity:
                self.stdout.write('Performing clean-up tasks')
            call_command('clearsessions', verbosity=verbosity)
            call_command('clear_oauth2_tokens', verbosity=verbosity)
        elif verbosity:
            self.stdout.write('Clean-up tasks disabled')
