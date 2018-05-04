from django.apps import AppConfig as DjangoAppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class AppConfig(DjangoAppConfig):
    name = 'core'
    verbose_name = _('Prisoner money')

    def ready(self):
        from django.contrib import admin
        from django.contrib.admin import sites as admin_sites
        from core.admin import site
        admin.site = site
        admin_sites.site = site

        from mtp_common import nomis
        nomis.get_client_token = get_client_token


def get_client_token():
    if getattr(settings, 'NOMIS_API_CLIENT_TOKEN', ''):
        return settings.NOMIS_API_CLIENT_TOKEN

    from core.models import Token

    try:
        return Token.objects.get(name='nomis').token
    except Token.DoesNotExist:
        pass
