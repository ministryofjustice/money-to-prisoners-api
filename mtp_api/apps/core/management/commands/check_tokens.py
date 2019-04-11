import datetime
import textwrap

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.utils.timezone import now
from mtp_common.tasks import send_email

from core.models import Token


class Command(BaseCommand):
    """
    Check if any tokens are going to expire in a week, email team and raise an error that's reported to Sentry
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        expiring = Token.objects.filter(expires__date=(now() + datetime.timedelta(days=7)).date())
        token_names = ', '.join('"%s"' % token for token in expiring)
        if token_names:
            send_email(
                settings.TEAM_EMAIL, 'core/expiring-tokens-email.txt',
                'Tokens are expiring in 7 days',
                context={'token_names': token_names},
                anymail_tags=['expiring-tokens'],
            )
            raise CommandError('These tokens are expiring in a week ' + token_names)
