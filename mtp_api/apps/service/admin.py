from django.contrib import admin

from service.models import Downtime


@admin.register(Downtime)
class DowntimeAdmin(admin.ModelAdmin):
    list_display = ('service', 'start', 'end')
