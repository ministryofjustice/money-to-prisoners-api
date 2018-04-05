from rest_framework import serializers

from core.models import FileDownload


class FileDownloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileDownload
        fields = ('label', 'date',)
