import json

from django.contrib import admin
from django.utils.html import format_html

from user_event_log.models import UserEvent


@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'kind', 'api_url_path')
    list_filter = ('kind',)
    list_select_related = ('user',)
    fields = (
        'id',
        'timestamp',
        'user',
        'kind',
        'api_url_path',
        'pretty_data',
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def pretty_data(self, obj):
        """Returns the data field formatted with indentation."""
        return format_html('<pre>{0}</pre>', json.dumps(obj.data, indent=2))

    pretty_data.short_description = 'data'
