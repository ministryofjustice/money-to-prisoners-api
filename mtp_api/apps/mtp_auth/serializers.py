from django.contrib.auth.models import User
from django.db.transaction import atomic

from rest_framework import serializers

from .models import (
    PrisonUserMapping, ApplicationGroupMapping, ApplicationUserMapping
)


class UserSerializer(serializers.ModelSerializer):
    prisons = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def get_prisons(self, obj):
        try:
            return list(obj.prisonusermapping.prisons.values_list('pk', flat=True))
        except PrisonUserMapping.DoesNotExist:
            return []

    def get_permissions(self, obj):
        return obj.get_all_permissions()

    @atomic
    def create(self, validated_data):
        new_user = super().create(validated_data)

        password = User.objects.make_random_password(length=10)
        new_user.set_password(password)

        # add application-user mapping
        client_application = self.context['request'].auth.application
        usermapping = ApplicationUserMapping.objects.create(
            user=new_user, application=client_application
        )
        new_user.applicationusermapping_set.add(usermapping)

        # add auth groups for application
        groupmappings = ApplicationGroupMapping.objects.filter(
            application__client_id=client_application.client_id
        )
        for groupmapping in groupmappings:
            new_user.groups.add(groupmapping.group)
        new_user.save()

        creating_user = self.context['request'].user
        prisons = PrisonUserMapping.objects.get_prison_set_for_user(creating_user)
        if len(prisons) > 0:
            pu = PrisonUserMapping.objects.create(user=new_user)
            for prison in prisons:
                pu.prisons.add(prison)
            pu.save()

        return new_user

    class Meta:
        model = User
        read_only_fields = ('pk',)
        fields = (
            'pk',
            'username',
            'first_name',
            'last_name',
            'email',
            'prisons',
            'permissions'
        )


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()
