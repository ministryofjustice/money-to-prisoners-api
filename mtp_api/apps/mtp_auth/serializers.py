from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.transaction import atomic
from django.utils.translation import gettext
from mtp_common.tasks import send_email
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import PrisonUserMapping, Role, ApplicationUserMapping, FailedLoginAttempt
from .validators import CaseInsensitiveUniqueValidator

User = get_user_model()


class RoleSerializer(serializers.ModelSerializer):
    application = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Role
        fields = (
            'name',
            'application',
        )

    def get_application(self, role):
        application = role.application
        return {
            'client_id': application.client_id,
            'name': application.name,
        }


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
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
            'roles',
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
            message=gettext('That email address already exists')
        ))

        return fields

    def get_is_locked_out(self, obj):
        return FailedLoginAttempt.objects.is_locked_out(user=obj)

    def get_roles(self, obj):
        return sorted(Role.objects.get_roles_for_user(obj).values_list('name', flat=True))

    def get_permissions(self, obj):
        return obj.get_all_permissions()

    def get_user_admin(self, obj):
        return obj.groups.filter(name='UserAdmin').exists()

    def get_prisons(self, obj):
        return (
            {
                'nomis_id': prison.pk,
                'name': prison.name,
                'pre_approval_required': prison.pre_approval_required
            }
            for prison in PrisonUserMapping.objects.get_prison_set_for_user(obj)
        )

    def validate(self, attrs):
        role = self.initial_data.get('role')
        if role:
            user = self.context['request'].user
            managed_roles = {
                role.name: role
                for role in Role.objects.get_managed_roles_for_user(user)
            }
            try:
                self.initial_data['role'] = managed_roles[role]
            except KeyError:
                raise serializers.ValidationError({'role': 'Invalid role: %s' % role})

        return super().validate(attrs)

    @atomic
    def create(self, validated_data):
        creating_user = self.context['request'].user

        role = validated_data.pop('role', None)
        make_user_admin = validated_data.pop('user_admin', False)
        validated_data.pop('is_locked_out', None)

        if not role:
            raise serializers.ValidationError({'role': 'Role must be specified'})

        new_user = super().create(validated_data)

        password = User.objects.make_random_password(length=10)
        new_user.set_password(password)
        new_user.save()

        if make_user_admin:
            new_user.groups.add(Group.objects.get(name='UserAdmin'))

        prisons = PrisonUserMapping.objects.get_prison_set_for_user(creating_user)
        if len(prisons) > 0:
            pu = PrisonUserMapping.objects.create(user=new_user)
            for prison in prisons:
                pu.prisons.add(prison)

        role.assign_to_user(new_user)

        context = {
            'username': new_user.username,
            'password': password,
            'service_name': role.application.name,
            'login_url': role.login_url,
        }
        send_email(
            new_user.email, 'mtp_auth/new_user.txt',
            gettext('Your new %(service_name)s account is ready to use') % {
                'service_name': role.application.name
            },
            context=context, html_template='mtp_auth/new_user.html',
            anymail_tags=['new-user'],
        )

        return new_user

    @atomic
    def update(self, user, validated_data):
        user_admin_group = Group.objects.get(name='UserAdmin')

        updating_user = self.context['request'].user
        was_user_admin = user.groups.filter(pk=user_admin_group.pk).exists()

        if user.pk == updating_user.pk and ('user_admin' in validated_data or 'role' in validated_data):
            # cannot edit one's own role or admin status
            raise serializers.ValidationError('Cannot change own access permissions')

        role = validated_data.pop('role', None)
        make_user_admin = validated_data.pop('user_admin', was_user_admin)
        is_locked_out = validated_data.pop('is_locked_out', None)

        updated_user = super().update(user, validated_data)

        if role:
            updated_user.applicationusermapping_set.all().delete()
            updated_user.groups.clear()

            if make_user_admin:
                updated_user.groups.add(user_admin_group)

            ApplicationUserMapping.objects.create(user=updated_user, application=role.application)
            for group in role.groups:
                updated_user.groups.add(group)
        elif was_user_admin != make_user_admin:
            if make_user_admin:
                updated_user.groups.add(user_admin_group)
            else:
                updated_user.groups.remove(user_admin_group)

        if is_locked_out is False:
            FailedLoginAttempt.objects.filter(user=updated_user).delete()

        return updated_user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()


class CreateNewPasswordSerializer(serializers.Serializer):
    password_change_url = serializers.CharField()
    reset_code_param = serializers.CharField()


class ResetPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(write_only=True)
    create_password = CreateNewPasswordSerializer(required=False)


class ChangePasswordWithCodeSerializer(serializers.Serializer):
    new_password = serializers.CharField()
