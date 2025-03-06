from django.apps import AppConfig as DjangoAppConfig
from django.utils.translation import gettext_lazy as _


class AppConfig(DjangoAppConfig):
    name = 'payment'
    verbose_name = _('Online Payments from GOV.UK Pay')
