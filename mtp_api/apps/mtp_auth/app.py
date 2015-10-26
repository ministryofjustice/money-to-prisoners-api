from django.apps import AppConfig as DjangoAppConfig


class AppConfig(DjangoAppConfig):
    name = 'mtp_auth'
    verbose_name = 'MTP Authorisation'
