import datetime

from django.utils import timezone
from django.utils.crypto import get_random_string
from oauth2_provider.models import Application, AccessToken

from mtp_auth.constants import (
    CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, SEND_MONEY_CLIENT_ID,
)


class AuthTestCaseMixin:
    APPLICATION_ID_MAP = {
        'PrisonerLocationAdmin': NOMS_OPS_OAUTH_CLIENT_ID,
        'Security': NOMS_OPS_OAUTH_CLIENT_ID,
        'BankAdmin': BANK_ADMIN_OAUTH_CLIENT_ID,
        'RefundBankAdmin': BANK_ADMIN_OAUTH_CLIENT_ID,
        'DisbursementBankAdmin': BANK_ADMIN_OAUTH_CLIENT_ID,
        'PrisonClerk': CASHBOOK_OAUTH_CLIENT_ID,
        'SendMoney': SEND_MONEY_CLIENT_ID,
    }

    def _get_http_authorization_token_for_user(self, user, client_id=None):
        if not client_id:
            group = user.groups.filter(name__in=self.APPLICATION_ID_MAP.keys()).first()
            if not group:
                return None
            client_id = self.APPLICATION_ID_MAP[group.name]
        application = Application.objects.get(client_id=client_id)

        token = get_random_string(length=35)
        AccessToken.objects.create(
            token=token,
            application=application,
            user=user,
            expires=timezone.now() + datetime.timedelta(days=30)
        )
        return token

    def get_http_authorization_for_user(self, user, client_id=None):
        token = self._get_http_authorization_token_for_user(
            user, client_id=client_id
        )
        return 'Bearer {0}'.format(token)
