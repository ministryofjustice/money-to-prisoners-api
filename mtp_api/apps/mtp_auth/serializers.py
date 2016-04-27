from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.mail import EmailMessage
from django.db.transaction import atomic
from django.template import loader
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import (
    PrisonUserMapping, ApplicationGroupMapping, ApplicationUserMapping
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    prisons = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    user_admin = serializers.SerializerMethodField()

    def get_fields(self):
        fields = super().get_fields()

        for field_name in ['first_name', 'last_name', 'email']:
            field = fields[field_name]
            field.required = True

        fields['email'].validators.append(UniqueValidator(
            User.objects.all(),
            message=_('A user with that email address already exists')
        ))

        return fields

    def get_prisons(self, obj):
        return list(
            PrisonUserMapping.objects.get_prison_set_for_user(obj)
            .values_list('pk', flat=True)
        )

    def get_permissions(self, obj):
        return obj.get_all_permissions()

    def get_user_admin(self, obj):
        return (obj.has_perm('auth.change_user') and
                obj.has_perm('auth.delete_user') and
                obj.has_perm('auth.add_user'))

    @atomic
    def create(self, validated_data):
        make_user_admin = validated_data.pop('user_admin', False)
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
        if make_user_admin:
            new_user.groups.add(Group.objects.get(name='UserAdmin'))
        new_user.save()

        creating_user = self.context['request'].user
        prisons = PrisonUserMapping.objects.get_prison_set_for_user(creating_user)
        if len(prisons) > 0:
            pu = PrisonUserMapping.objects.create(user=new_user)
            for prison in prisons:
                pu.prisons.add(prison)
            pu.save()

        context = {
            'username': new_user.username,
            'password': password,
            'app': client_application.name
        }
        body = loader.get_template('mtp_auth/new_user.txt').render(context)
        email = EmailMessage(
            _('Your new Money To Prisoners %(app)s account') % {'app': client_application.name},
            body,
            settings.MAILGUN_FROM_ADDRESS,
            [new_user.email]
        )
        email.send()

        return new_user

    @atomic
    def update(self, user, validated_data):
        make_user_admin = validated_data.pop('user_admin', None)
        updated_user = super().update(user, validated_data)

        if make_user_admin is not None:
            user_admin_group = Group.objects.get(name='UserAdmin')
            if make_user_admin:
                updated_user.groups.add(user_admin_group)
            else:
                updated_user.groups.remove(user_admin_group)
        updated_user.save()

        return updated_user

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
            'permissions',
            'user_admin'
        )


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()


class ResetPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(write_only=True)
