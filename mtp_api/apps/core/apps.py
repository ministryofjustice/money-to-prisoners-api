from django.apps import AppConfig as DjangoAppConfig
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
