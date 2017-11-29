from django.contrib import admin

from service.models import Downtime, Notification


@admin.register(Downtime)
class DowntimeAdmin(admin.ModelAdmin):
    list_display = ('service', 'start', 'end', 'message_to_users')
    list_filter = ('service',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('headline', 'target', 'level', 'start', 'end')
    list_filter = ('target', 'level')
