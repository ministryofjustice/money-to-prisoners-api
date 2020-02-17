from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import get_default_password_validators
from django.core.exceptions import ObjectDoesNotExist
from django.db.transaction import atomic
from django.utils.text import capfirst
from django.utils.translation import gettext, gettext_lazy as _
from mtp_common.tasks import send_email
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from mtp_auth.models import (
    ApplicationUserMapping, PrisonUserMapping, Role, Flag,
    FailedLoginAttempt, AccountRequest, JobInformation
)
from mtp_auth.validators import CaseInsensitiveUniqueValidator
from prison.models import Prison

User = get_user_model()


def generate_new_password():
    from django.forms import ValidationError

    validators = get_default_password_validators()
    for __ in range(5):
        password = User.objects.make_random_password(length=10)
        try:
            for validator in validators:
                validator.validate(password)
        except ValidationError:
            continue
        return password


class JobInformationSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobInformation
        fields = ('title',
                  'prison_estate',
                  'tasks',
                  )

    def create(self, validated_data):
        user = self.context['request'].user
        user.flags.create(name='provided-job-information')
        validated_data['user'] = user
        return super().create(validated_data)


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
    flags = serializers.SlugRelatedField(slug_field='name', read_only=True, many=True)
    permissions = serializers.SerializerMethodField()
    user_admin = serializers.SerializerMethodField()
    prisons = serializers.SerializerMethodField()
    is_locked_out = serializers.SerializerMethodField()

    allowed_self_updates = {'first_name', 'last_name', 'email', 'prisons'}

    class Meta:
        model = User
        read_only_fields = ('pk', 'flags')
        fields = (
            'pk',
            'username',
            'first_name',
            'last_name',
            'email',
            'is_active',
            'roles',
            'flags',
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
                for role in Role.objects.get_roles_for_user(user)
            }
            try:
                self.initial_data['role'] = managed_roles[role]
            except KeyError:
                raise serializers.ValidationError({'role': 'Invalid role: %s' % role})

        prisons = self.initial_data.get('prisons')
        if prisons is not None:
            prison_objects = Prison.objects.filter(
                nomis_id__in=[prison['nomis_id'] for prison in prisons]
            )
            attrs['prisons'] = prison_objects

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

        password = generate_new_password()
        new_user.set_password(password)
        new_user.save()

        if make_user_admin:
            new_user.groups.add(Group.objects.get(name='UserAdmin'))

        PrisonUserMapping.objects.assign_prisons_from_user(creating_user, new_user)
        role.assign_to_user(new_user)

        context = {
            'username': new_user.username,
            'password': password,
            'service_name': role.application.name.lower(),
            'login_url': role.login_url,
        }
        send_email(
            new_user.email, 'mtp_auth/new_user.txt',
            capfirst(gettext('Your new %(service_name)s account is ready to use') % context),
            context=context, html_template='mtp_auth/new_user.html',
            anymail_tags=['new-user'],
        )

        return new_user

    @atomic
    def update(self, user, validated_data):
        user_admin_group = Group.objects.get(name='UserAdmin')

        updating_user = self.context['request'].user
        was_user_admin = user.groups.filter(pk=user_admin_group.pk).exists()

        if user.pk == updating_user.pk and any(field not in self.allowed_self_updates for field in validated_data):
            # cannot edit one's own role, admin status, etc
            raise serializers.ValidationError('Cannot change own access permissions')

        role = validated_data.pop('role', None)
        make_user_admin = validated_data.pop('user_admin', was_user_admin)
        is_locked_out = validated_data.pop('is_locked_out', None)
        prisons = validated_data.pop('prisons', None)

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

        if prisons is not None:
            if updated_user.pk != updating_user.pk:
                raise serializers.ValidationError("Cannot change another user's prisons")
            user_group_names = updated_user.groups.values_list('name', flat=True)
            if 'Security' in user_group_names and 'UserAdmin' not in user_group_names:
                PrisonUserMapping.objects.assign_prisons_to_user(updated_user, prisons)
            else:
                raise serializers.ValidationError('Only security users can change prisons')

        return updated_user


class FlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flag
        fields = ('user', 'name')

    def to_representation(self, instance):
        return instance.name


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


class UniqueKeyRelatedField(serializers.PrimaryKeyRelatedField):
    def __init__(self, unique_key, **kwargs):
        super().__init__(**kwargs)
        self.unique_key = unique_key

    def use_pk_only_optimization(self):
        return self.unique_key == 'pk'

    def to_internal_value(self, data):
        try:
            return self.get_queryset().get(**{self.unique_key: data})
        except ObjectDoesNotExist:
            self.fail('does_not_exist', pk_value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)

    def to_representation(self, value):
        return getattr(value, self.unique_key)


class AccountRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountRequest
        fields = '__all__'
        validators = [
            serializers.UniqueTogetherValidator(
                queryset=AccountRequest.objects.all(),
                fields=('role', 'username'),
                message=_('You have already requested access to this service')
            )
        ]

    def get_fields(self):
        fields = super().get_fields()
        fields['role'] = UniqueKeyRelatedField(unique_key='name', queryset=Role.objects.all())
        return fields
