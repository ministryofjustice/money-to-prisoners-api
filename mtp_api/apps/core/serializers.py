from rest_framework import serializers

from core.models import FileDownload, Token


class FileDownloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileDownload
        fields = ('label', 'date',)


# TODO: Remove once all apps move to NOMIS Elite2
class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Token
        fields = ('token', 'expires',)


class NullSerializer(serializers.Serializer):
    # Necessary so that django-rest-framework-swagger can introspect the serializers of all APIView/APIViewSets
    # even those which don't return
    pass
