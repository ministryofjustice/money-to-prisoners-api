from django.contrib.auth.models import User

from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    prisons = serializers.SerializerMethodField()

    def get_prisons(self, obj):
        return [
            prison.pk for prison in obj.prisonusermapping.prisons.all()
        ]

    class Meta:
        model = User
        fields = (
            'pk',
            'username',
            'first_name',
            'last_name',
            'prisons'
        )
