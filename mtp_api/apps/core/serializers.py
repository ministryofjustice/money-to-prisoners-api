from rest_framework import serializers

from core.models import FileDownload, Token


class FileDownloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileDownload
        fields = ('label', 'date',)


class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = ('token', 'expires',)
