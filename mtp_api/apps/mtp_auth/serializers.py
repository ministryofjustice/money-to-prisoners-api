from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.transaction import atomic
from django.utils.translation import gettext as _
from mtp_common.email import send_email
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import (
    PrisonUserMapping, ApplicationGroupMapping, ApplicationUserMapping,
    FailedLoginAttempt,
)
from .validators import CaseInsensitiveUniqueValidator

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    applications = serializers.SerializerMethodField(read_only=True)
    permissions = serializers.SerializerMethodField(read_only=True)
    user_admin = serializers.SerializerMethodField()
    prisons = serializers.SerializerMethodField()
    is_locked_out = serializers.SerializerMethodField()

    class Meta:
        model = User
        read_only_fields = ('pk',)
        fields = (
            'pk',
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'applications',
            'permissions',
            'user_admin',
            'prisons',
            'is_locked_out',
        )
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True},
        }

    def get_fields(self):
        fields = super().get_fields()

        username_validators = list(filter(lambda validator: not isinstance(validator, UniqueValidator),
                                          fields['username'].validators))
        username_validators.append(
            CaseInsensitiveUniqueValidator(User.objects.all(),
                                           User._meta.get_field('username').error_messages['unique'])
        )
        fields['username'].validators = username_validators

        fields['email'].validators.append(UniqueValidator(
            User.objects.all(),
            message=_('That email address already exists')
        ))

        return fields

    def get_is_locked_out(self, obj):
        return FailedLoginAttempt.objects.is_locked_out(user=obj)

    def get_applications(self, obj):
        return sorted(application.application.name for application in ApplicationUserMapping.objects.filter(user=obj))

    def get_permissions(self, obj):
        return obj.get_all_permissions()

    def get_user_admin(self, obj):
        return (obj.has_perm('auth.change_user') and
                obj.has_perm('auth.delete_user') and
                obj.has_perm('auth.add_user'))

    def get_prisons(self, obj):
        return (
            {
                'nomis_id': prison.pk,
                'name': prison.name,
                'pre_approval_required': prison.pre_approval_required
            }
            for prison in PrisonUserMapping.objects.get_prison_set_for_user(obj)
        )

    @atomic
    def create(self, validated_data):
        creating_user = self.context['request'].user
        make_user_admin = validated_data.pop('user_admin', False)
        validated_data.pop('is_locked_out', None)
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
            if groupmapping.group in creating_user.groups.all():
                new_user.groups.add(groupmapping.group)
        if make_user_admin:
            new_user.groups.add(Group.objects.get(name='UserAdmin'))
        new_user.save()

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
        send_email(
            new_user.email, 'mtp_auth/new_user.txt',
            _('Your new %(app)s account is ready to use') % {'app': client_application.name},
            context=context, html_template='mtp_auth/new_user.html'
        )

        return new_user

    @atomic
    def update(self, user, validated_data):
        make_user_admin = validated_data.pop('user_admin', None)
        is_locked_out = validated_data.pop('is_locked_out', None)
        updated_user = super().update(user, validated_data)

        if make_user_admin is not None:
            user_admin_group = Group.objects.get(name='UserAdmin')
            if make_user_admin:
                updated_user.groups.add(user_admin_group)
            else:
                updated_user.groups.remove(user_admin_group)
        updated_user.save()

        if is_locked_out is False:
            FailedLoginAttempt.objects.filter(user=updated_user).delete()

        return updated_user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()


class ResetPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(write_only=True)
