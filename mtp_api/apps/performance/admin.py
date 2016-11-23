from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.utils.translation import gettext_lazy as _

from core.admin import add_short_description
from performance.models import DigitalTakeup


@admin.register(DigitalTakeup)
class DigitalTakeupAdmin(ModelAdmin):
    list_display = ('start_date', 'end_date', 'prison', 'digital_takeup')
    list_filter = ('prison',)
    ordering = ('-start_date', 'prison__name')
    date_hierarchy = 'start_date'

    @add_short_description(_('digital take-up'))
    def digital_takeup(self, instance):
        return instance.formatted_digital_takeup
