from django.contrib.auth.models import User

from rest_framework import serializers

from .models import PrisonUserMapping


class UserSerializer(serializers.ModelSerializer):
    prisons = serializers.SerializerMethodField()

    def get_prisons(self, obj):
        try:
            return list(obj.prisonusermapping.prisons.values_list('pk', flat=True))
        except PrisonUserMapping.DoesNotExist:
            return []

    class Meta:
        model = User
        fields = (
            'pk',
            'username',
            'first_name',
            'last_name',
            'prisons'
        )
