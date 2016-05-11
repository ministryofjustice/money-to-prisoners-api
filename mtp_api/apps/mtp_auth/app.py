from django.apps import AppConfig as DjangoAppConfig
from django.utils.translation import gettext_lazy as _


class AppConfig(DjangoAppConfig):
    name = 'mtp_auth'
    verbose_name = 'MTP Authorisation'

    def ready(self):
        from django.contrib.auth import get_user_model

        field = get_user_model()._meta.get_field('username')
        field.error_messages['unique'] = _('That username already exists')
