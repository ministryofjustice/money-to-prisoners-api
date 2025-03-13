from django.apps import AppConfig as DjangoAppConfig
from django.utils.translation import gettext_lazy


class AppConfig(DjangoAppConfig):
    name = 'user_event_log'
    verbose_name = gettext_lazy('User Event Log')
