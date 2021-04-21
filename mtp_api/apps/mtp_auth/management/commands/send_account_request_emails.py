import datetime
import logging

from django.contrib.postgres.aggregates import ArrayAgg
from django.core.management import BaseCommand
from django.db import models
from django.db.models.functions import Concat
from django.utils.text import capfirst
from django.utils.timezone import now
from django.utils.translation import gettext
from mtp_common.tasks import send_email

from mtp_auth.models import AccountRequest, Role
from prison.models import Prison

logger = logging.getLogger('mtp')


class Command(BaseCommand):
    """
    Emails user admins that have pending account requests

    Sends an email to all admins for the user's team who have pending requests created
    *any time yesterday*. This command should only be scheduled once a day.

    TODO: only currently handles teams based on role AND prison, i.e. only applicable to cashbook self-sign-up
    """
    help = __doc__.strip().splitlines()[0]

    def handle(self, *args, **options):
        grouped_requests = AccountRequest.objects.filter(
            created__date=now() - datetime.timedelta(days=1)
        ).order_by().values('role', 'prison').annotate(
            names=ArrayAgg(Concat('first_name', models.Value(' '), 'last_name'))
        )
        for group in grouped_requests:
            if group['prison']:
                prison = Prison.objects.get(pk=group['prison'])
            else:
                prison = None

            role = Role.objects.get(pk=group['role'])
            names = group['names']
            admins = self.find_admins(role, prison)
            if admins:
                self.email_admins(admins, role, names)
            else:
                logger.error(
                    'No active user admins for role in prison for %(role_name)s in %(prison_name)s',
                    {'role_name': role.name, 'prison_name': prison.name}
                )

    def find_admins(self, role, prison):
        admins = role.key_group.user_set.filter(
            is_active=True, is_superuser=False
        ).filter(groups__name='UserAdmin')

        # 'security' requests are sent to all UserAdmins/FIU regardless of prison
        if role.name != 'security':
            admins = admins.filter(prisonusermapping__prisons=prison)

        return list(admins)

    def email_admins(self, admins, role, names):
        service_name = role.application.name.lower()
        send_email(
            [admin.email for admin in admins],
            'mtp_auth/new_account_requests.txt',
            capfirst(gettext('You have new %(service_name)s users to approve') % {
                'service_name': service_name,
            }),
            context={
                'service_name': service_name,
                'names': names,
                'login_url': role.login_url,
            },
            html_template='mtp_auth/new_account_requests.html',
            anymail_tags=['new-account-requests'],
        )
