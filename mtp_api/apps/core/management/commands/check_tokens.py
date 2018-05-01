import datetime
import textwrap

from django.core.management import BaseCommand, CommandError
from django.utils.timezone import now

from core.models import Token


class Command(BaseCommand):
    """
    Check if any tokens are going to expire in a week, raise an error that's reported to Sentry
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        expiring = Token.objects.filter(expires__date=(now() + datetime.timedelta(days=7)).date())
        names = ', '.join('"%s"' % token for token in expiring)
        if names:
            raise CommandError('These tokens are expiring in a week ' + names)
