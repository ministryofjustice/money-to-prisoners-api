from django.contrib import admin

from notification.models import Event, EmailNotificationPreferences


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('rule', 'description')


@admin.register(EmailNotificationPreferences)
class EmailNotificationPreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'frequency')
