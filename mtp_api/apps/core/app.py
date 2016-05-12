from django.apps import AppConfig as DjangoAppConfig
from django.contrib import admin
from django.contrib.admin import sites as admin_sites
from django.utils.translation import gettext_lazy as _

from core.admin import site

admin.site = site
admin_sites.site = site


class AppConfig(DjangoAppConfig):
    name = 'core'
    verbose_name = _('MTP')
