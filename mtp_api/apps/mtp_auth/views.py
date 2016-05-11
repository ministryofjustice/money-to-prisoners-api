from functools import reduce
import logging

from django.conf import settings
from django.contrib.auth import password_validation, get_user_model
from django.contrib.auth.password_validation import get_default_password_validators
from django.core.exceptions import NON_FIELD_ERRORS
from django.core.mail import EmailMessage
from django.db.models import Q
from django.db.transaction import atomic
from django.forms import ValidationError
from django.http import Http404
from django.template import loader
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets, mixins, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import FailedLoginAttempt, PrisonUserMapping
from .permissions import UserPermissions, AnyAdminClientIDPermissions
from .serializers import UserSerializer, ChangePasswordSerializer, ResetPasswordSerializer

User = get_user_model()

logger = logging.getLogger('mtp')


class UserViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin,
                  mixins.UpdateModelMixin, mixins.CreateModelMixin,
                  mixins.DestroyModelMixin, viewsets.GenericViewSet):
    lookup_field = 'username'
    lookup_value_regex = '[^/]+'

    queryset = User.objects.none()
    permission_classes = (IsAuthenticated, UserPermissions)
    serializer_class = UserSerializer

    def get_queryset(self):
        client_id = self.request.auth.application.client_id
        queryset = User.objects.filter(
            applicationusermapping__application__client_id=client_id,
            is_active=True
        )

        user_prisons = PrisonUserMapping.objects.get_prison_set_for_user(self.request.user)
        if len(user_prisons) > 0:
            prison_filters = []
            for prison in user_prisons:
                prison_filters.append(Q(prisonusermapping__prisons=prison))
            queryset = queryset.filter(
                reduce(lambda a, b: a | b, prison_filters)).distinct()
        return queryset

    def get_object(self, *args, **kwargs):
        """
        Make sure that you can only access your own user data,
        unless the user is a UserAdmin.
        """
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup = self.kwargs.get(lookup_url_kwarg, None)

        if (lookup == self.request.user.username or
                self.request.user.has_perm('auth.change_user')):
            return super(UserViewSet, self).get_object(*args, **kwargs)
        else:
            raise Http404()

    def perform_create(self, serializer):
        if 'user_admin' in self.request.data:
            serializer.save(user_admin=self.request.data['user_admin'])
        else:
            serializer.save()

    def perform_update(self, serializer):
        if 'user_admin' in self.request.data:
            serializer.save(user_admin=self.request.data['user_admin'])
        else:
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user != request.user:
            user.is_active = False
            user.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={
                    '__all__': [_('You cannot delete yourself')]
                },
            )


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated, AnyAdminClientIDPermissions)
    serializer_class = ChangePasswordSerializer

    @atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            try:
                if not FailedLoginAttempt.objects.is_locked_out(
                        request.user, request.auth.application):
                    if request.user.check_password(old_password):
                        FailedLoginAttempt.objects.delete_failed_attempts(
                            request.user, request.auth.application)
                        password_validation.validate_password(new_password, request.user)
                        request.user.set_password(new_password)
                        request.user.save()
                        return Response(status=status.HTTP_204_NO_CONTENT)
                    else:
                        FailedLoginAttempt.objects.add_failed_attempt(
                            request.user, request.auth.application)
                errors = {'old_password': [_('You’ve entered an incorrect password')]}
            except ValidationError as e:
                errors = {'new_password': e.error_list}
        else:
            errors = serializer.errors
        return Response(
            data={'errors': errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class ResetPasswordView(generics.GenericAPIView):
    permission_classes = ()
    queryset = User.objects.all()
    serializer_class = ResetPasswordSerializer

    error_messages = {
        'generic': _('There has been a system error. Please try again later'),
        'not_found': _('Username doesn’t match any user account'),
        'locked_out': _('Your account is locked, '
                        'please contact the person who set it up'),
        'no_email': _('We don’t have your email address, '
                      'please contact the person who set up the account'),
    }

    @classmethod
    def generate_new_password(cls):
        validators = get_default_password_validators()
        for __ in range(5):
            password = User.objects.make_random_password(length=10)
            try:
                for validator in validators:
                    validator.validate(password)
            except ValidationError:
                continue
            return password

    def failure_response(self, errors, field=NON_FIELD_ERRORS):
        if isinstance(errors, str):
            errors = {
                field: [self.error_messages[errors]]
            }
        return Response(
            data={'errors': errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            try:
                user = self.queryset.get(username=serializer.validated_data['username'])
            except User.DoesNotExist:
                return self.failure_response('not_found', field='username')
            if FailedLoginAttempt.objects.is_locked_out(user):
                return self.failure_response('locked_out', field='username')
            if not user.email:
                return self.failure_response('no_email', field='username')

            password = self.generate_new_password()
            if not password:
                logger.error('Password could not be generated; have validators changed?')
                return self.failure_response('generic')

            user.set_password(password)
            user.save()

            email_body = loader.get_template('mtp_auth/reset-password.txt').render({
                'username': user.username,
                'password': password,
            }).strip()
            email = EmailMessage(
                subject=_('Your new Money To Prisoners password'),
                body=email_body,
                from_email=settings.MAILGUN_FROM_ADDRESS,
                to=[user.email]
            )
            email.send()

            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return self.failure_response(serializer.errors)
