from rest_framework import serializers

from service.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    level = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ('target', 'level', 'start', 'end', 'headline', 'message')

    def get_level(self, notification):
        return notification.level_label
