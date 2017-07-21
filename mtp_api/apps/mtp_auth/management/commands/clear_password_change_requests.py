from datetime import timedelta
import textwrap

from django.core.management import BaseCommand
from django.utils.timezone import now
from mtp_auth.models import PasswordChangeRequest


class Command(BaseCommand):
    """
    Clear expired password change requests.
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)
        requests = PasswordChangeRequest.objects.filter(created__lte=now() - timedelta(hours=12))
        if verbosity:
            msg = 'Deleting %d expired password change request(s)' % requests.count()
            self.stdout.write(msg)
        requests.delete()
