import textwrap

from django.core.management import BaseCommand
from django.utils.timezone import now
from oauth2_provider.models import AccessToken


class Command(BaseCommand):
    """
    Clear expired OAuth2 tokens.
    The module `oauth2_provider` does not provide a way to do this.
    """
    help = textwrap.dedent(__doc__).strip()

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)
        tokens = AccessToken.objects.filter(expires__lte=now())
        if verbosity:
            msg = 'Deleting %d expired OAuth2 access token(s)' % tokens.count()
            self.stdout.write(msg)
        tokens.delete()
