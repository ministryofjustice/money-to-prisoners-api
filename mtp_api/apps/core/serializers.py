from rest_framework import serializers

from core.models import FileDownload


class FileDownloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileDownload
        fields = ('label', 'date',)


class NullSerializer(serializers.Serializer):
    # Necessary so that django-rest-framework-swagger can introspect the serializers of all APIView/APIViewSets
    # even those which don't return
    pass
