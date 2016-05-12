from django.apps import AppConfig as DjangoAppConfig
from django.utils.translation import gettext_lazy as _


class AppConfig(DjangoAppConfig):
    name = 'prison'
    verbose_name = _('Prisons')
