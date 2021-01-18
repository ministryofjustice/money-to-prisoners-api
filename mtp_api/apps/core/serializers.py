from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.models import FileDownload

User = get_user_model()


class FileDownloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileDownload
        fields = ('label', 'date',)


class NullSerializer(serializers.Serializer):
    # Necessary so that django-rest-framework-swagger can introspect the serializers of all APIView/APIViewSets
    # even those which don't return
    pass


class BasicUserSerializer(serializers.ModelSerializer):
    class Meta:
        ref_name = 'Basic User'
        model = User
        fields = (
            'username',
            'first_name',
            'last_name',
        )
