from django.contrib import admin

from notification.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('rule', 'description')
