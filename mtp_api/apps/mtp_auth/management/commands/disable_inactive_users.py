from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError
from django.db.models import Q
from django.utils.timezone import now
from oauth2_provider.models import Application

from mtp_auth.constants import CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID

User = get_user_model()


class Command(BaseCommand):
    """
    Deactivate users who have not logged in for a while.
    Only applies to regular users with access to particular apps.
    """
    help = __doc__.strip().splitlines()[0]

    inactive_months = 3
    applications = [CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID]

    def handle(self, *args, **options):
        verbosity = options['verbosity']

        cutoff_date = now() - relativedelta(months=self.inactive_months)
        admin_cutoff_date = now() - relativedelta(months=self.inactive_months * 2)

        applications = list(Application.objects.filter(client_id__in=self.applications).values_list('pk', flat=True))
        if len(applications) != len(self.applications):
            raise CommandError('Could not find all oauth applications')

        if verbosity > 0:
            self.stderr.write(f'Looking for users who’ve not logged in since {cutoff_date}')

        users = User.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False,
            applicationusermapping__application__in=applications,
        ).filter(
            # last login was a long time ago
            Q(last_login__lt=cutoff_date) |
            # or never logged in but joined a long time ago
            Q(last_login__isnull=True) & Q(date_joined__lt=cutoff_date)
        ).distinct('username')
        for user in users:
            if user.groups.filter(name='UserAdmin').exists():
                if (
                    user.last_login and user.last_login >= admin_cutoff_date or
                    user.last_login is None and user.date_joined >= admin_cutoff_date
                ):
                    continue
            if verbosity > 0:
                self.stderr.write(f'Deactivating {user.username}')
            user.is_active = False
            user.save()
