from django.apps import AppConfig as DjangoAppConfig
from django.utils.translation import gettext_lazy as _


class AppConfig(DjangoAppConfig):
    name = 'mtp_auth'
    verbose_name = _('MTP Authorisation')

    def ready(self):
        from mtp_auth.models import patch_user_model

        patch_user_model()
