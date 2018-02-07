import textwrap

from django.core.management import BaseCommand, call_command
from mtp_common.stack import StackException, is_first_instance


class Command(BaseCommand):
    """
    Perform periodic clean-up removing expired DB models.
    This is designed to run on only one instance in an auto-scaling group.
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        verbosity = options['verbosity']
        try:
            run_cleanup_tasks = is_first_instance()
        except StackException:
            run_cleanup_tasks = True
        if run_cleanup_tasks:
            if verbosity:
                self.stdout.write('Performing clean-up tasks')
            call_command('clearsessions', verbosity=verbosity)
            call_command('clear_oauth2_tokens', verbosity=verbosity)
            call_command('clear_password_change_requests', verbosity=verbosity)
            call_command('clear_abandoned_payments', age=7, verbosity=verbosity)
        elif verbosity:
            self.stdout.write('Clean-up tasks do not run on secondary instances')
