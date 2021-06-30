from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.utils.translation import gettext_lazy as _

from core.admin import add_short_description
from performance.models import DigitalTakeup, PerformanceData, UserSatisfaction
from transaction.utils import format_percentage


@admin.register(DigitalTakeup)
class DigitalTakeupAdmin(ModelAdmin):
    list_display = ('date', 'prison', 'digital_takeup')
    list_filter = ('prison',)
    ordering = ('-date', 'prison__name')
    date_hierarchy = 'date'

    @add_short_description(_('digital take-up'))
    def digital_takeup(self, instance):
        return instance.formatted_digital_takeup


@admin.register(UserSatisfaction)
class UserSatisfactionAdmin(ModelAdmin):
    list_display = ('date', *UserSatisfaction.rating_field_names)
    ordering = ('-date',)
    date_hierarchy = 'date'


@admin.register(PerformanceData)
class PerformanceDataAdmin(ModelAdmin):
    list_display = (
        'week',
        'credits_total',
        'credits_by_mtp',
        'view_digital_takeup',
        'view_completion_rate',
        'view_user_satisfaction',
        *PerformanceData.rating_field_names,
    )
    ordering = ('-week',)
    date_hierarchy = 'week'

    @add_short_description(_('Digital take-up'))
    def view_digital_takeup(self, obj):
        return self._as_percentage(obj.digital_takeup)

    @add_short_description(_('Completion rate'))
    def view_completion_rate(self, obj):
        return self._as_percentage(obj.completion_rate)

    @add_short_description(_('User satisfaction'))
    def view_user_satisfaction(self, obj):
        return self._as_percentage(obj.user_satisfaction)

    def _as_percentage(self, value):
        if value:
            return format_percentage(value)
