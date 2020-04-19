import collections
import logging
from urllib.parse import urlsplit, urlunsplit, urlencode, parse_qs

from django.conf import settings
from django.contrib.admin.models import LogEntry, CHANGE as CHANGE_LOG_ENTRY, DELETION as DELETION_LOG_ENTRY
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.auth import password_validation, get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import NON_FIELD_ERRORS
from django.db import connection
from django.db.transaction import atomic
from django.forms import ValidationError
from django.http import Http404
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.decorators import method_decorator
from django.utils.text import capfirst
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from mtp_common.tasks import send_email
from oauth2_provider.models import Application
from rest_framework import viewsets, generics, status
from rest_framework.exceptions import ValidationError as RestValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings

from core.views import BaseAdminReportView
from mtp_auth.forms import LoginStatsForm
from mtp_auth.models import (
    ApplicationUserMapping, PrisonUserMapping, Role, Flag,
    FailedLoginAttempt, PasswordChangeRequest, AccountRequest, Login,
)
from mtp_auth.permissions import UserPermissions, AnyAdminClientIDPermissions, AccountRequestPremissions
from mtp_auth.serializers import (
    RoleSerializer, UserSerializer, FlagSerializer, AccountRequestSerializer,
    ChangePasswordSerializer, ResetPasswordSerializer, ChangePasswordWithCodeSerializer,
    generate_new_password, JobInformationSerializer
)
from prison.models import Prison

User = get_user_model()

logger = logging.getLogger('mtp')


class RoleViewSet(viewsets.mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Role.objects.all()
    permission_classes = (IsAuthenticated,)
    serializer_class = RoleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if 'managed' in self.request.query_params:
            user = self.request.user
            managed_roles = Role.objects.get_roles_for_user(user)
            queryset = queryset.filter(pk__in=set(role.pk for role in managed_roles))
        return queryset


class JobInformationViewSet(viewsets.mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = JobInformationSerializer


def get_managed_user_queryset(user):
    """
    Set of users for user account management AND looking up details of self.
    If request user is a super admin, they only get themselves back.
    If request user has more than one role, they get just themselves back.
    Otherwise returns all users who have the same role (determined by key group) AND matching prison set.
    Inactive users are always returned.

    NB: Does not check that the user has management permissions
    """
    user_key_groups = list(user.groups.filter(
        pk__in=Role.objects.values_list('key_group')
    ).values_list('pk', flat=True))
    if len(user_key_groups) != 1 or user.is_superuser:
        return User.objects.filter(pk=user.pk)
    user_key_group = user_key_groups[0]

    queryset = User.objects.exclude(is_superuser=True).filter(groups=user_key_group).order_by('username')

    prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(user).values_list('pk', flat=True))
    if prisons:
        for prison in prisons:
            queryset = queryset.filter(prisonusermapping__prisons=prison)
    else:
        queryset = queryset.filter(prisonusermapping__isnull=True)

    return queryset


class UserViewSet(viewsets.ModelViewSet):
    lookup_field = 'username__iexact'
    lookup_url_kwarg = 'username'
    lookup_value_regex = '[^/]+'

    queryset = User.objects.none()
    permission_classes = (IsAuthenticated, UserPermissions)
    serializer_class = UserSerializer

    def get_queryset(self):
        return get_managed_user_queryset(self.request.user)

    def get_object(self):
        """
        Make sure that you can only access your own user data,
        unless the user is a UserAdmin.
        """
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup = self.kwargs.get(lookup_url_kwarg, None)

        if (lookup.lower() == self.request.user.username.lower() or
                self.request.user.has_perm('auth.change_user')):
            return super().get_object()
        else:
            raise Http404()

    def perform_create_or_update(self, serializer):
        kwargs = {
            key: self.request.data[key]
            for key in ('user_admin', 'is_locked_out', 'role')
            if key in self.request.data
        }
        serializer.save(**kwargs)

    def perform_create(self, serializer):
        self.perform_create_or_update(serializer)

    def perform_update(self, serializer):
        self.perform_create_or_update(serializer)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if request.user == user or request.user.has_perm('auth.delete_user'):
            self.perform_destroy(user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={
                    api_settings.NON_FIELD_ERRORS_KEY: [_('You cannot delete other users')]
                },
            )

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()


class UserFlagViewSet(viewsets.mixins.DestroyModelMixin, viewsets.mixins.ListModelMixin, viewsets.GenericViewSet):
    lookup_field = 'name'
    queryset = Flag.objects.all()
    permission_classes = (IsAuthenticated,)
    serializer_class = FlagSerializer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        user = request.user
        if user.has_perm('auth.change_user'):
            queryset = get_managed_user_queryset(user)
        else:
            queryset = User.objects.filter(pk=user.pk)
        try:
            self.user = queryset.get(username=self.kwargs.get('user_username'))
        except User.DoesNotExist:
            raise Http404

    def get_queryset(self):
        return super().get_queryset().filter(user=self.user)

    def update(self, request, *args, **kwargs):
        try:
            self.get_object()
            return Response({}, status=status.HTTP_200_OK)
        except Http404:
            data = {
                'user': self.user.pk,
                'name': kwargs.get('name') or '',
            }
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response({}, status=status.HTTP_201_CREATED)


@method_decorator(sensitive_post_parameters('old_password', 'new_password'), name='dispatch')
class ChangePasswordView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated, AnyAdminClientIDPermissions)
    serializer_class = ChangePasswordSerializer

    @atomic
    @method_decorator(sensitive_variables('old_password', 'new_password'))
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


@method_decorator(sensitive_post_parameters('new_password'), name='dispatch')
class ChangePasswordWithCodeView(generics.GenericAPIView):
    permission_classes = ()
    serializer_class = ChangePasswordWithCodeSerializer

    @atomic
    @method_decorator(sensitive_variables('new_password'))
    def post(self, request, code):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            new_password = serializer.validated_data['new_password']

            try:
                user = PasswordChangeRequest.objects.get(code=code).user
                password_validation.validate_password(new_password, user)
                user.set_password(new_password)
                user.save()
                return Response(status=status.HTTP_204_NO_CONTENT)
            except PasswordChangeRequest.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)
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
    serializer_class = ResetPasswordSerializer
    immutable_users = ['transaction-uploader', 'send-money']

    error_messages = {
        'generic': _('There has been a system error. Please try again later'),
        'not_found': _('Username doesn’t match any user account'),
        'locked_out': _('Your account is locked, '
                        'please contact the person who set it up'),
        'no_email': _('We don’t have your email address, '
                      'please contact the person who set up the account'),
        'multiple_found': _('That email address matches multiple user accounts, '
                            'please enter your unique username'),
    }

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
    @method_decorator(sensitive_variables('password'))
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user_identifier = serializer.validated_data['username']
            try:
                user = User.objects.get_by_natural_key(user_identifier)
            except User.DoesNotExist:
                users = User.objects.filter(email__iexact=user_identifier)
                user_count = users.count()
                if user_count == 0:
                    return self.failure_response('not_found', field='username')
                elif user_count > 1:
                    return self.failure_response('multiple_found', field='username')
                user = users[0]
            if user.username in self.immutable_users:
                return self.failure_response('not_found', field='username')
            if user.is_locked_out:
                return self.failure_response('locked_out', field='username')
            if not user.email:
                return self.failure_response('no_email', field='username')

            service_name = gettext('Prisoner Money').lower()
            if serializer.validated_data.get('create_password'):
                change_request, _ = PasswordChangeRequest.objects.get_or_create(user=user)
                change_password_url = urlsplit(
                    serializer.validated_data['create_password']['password_change_url']
                )
                query = parse_qs(change_password_url.query)
                query.update({
                    serializer.validated_data['create_password']['reset_code_param']: str(change_request.code)
                })
                change_password_url = list(change_password_url)
                change_password_url[3] = urlencode(query)
                change_password_url = urlunsplit(change_password_url)
                send_email(
                    user.email, 'mtp_auth/create_new_password.txt',
                    capfirst(gettext('Create a new %(service_name)s password') % {
                        'service_name': service_name,
                    }),
                    context={
                        'service_name': service_name,
                        'change_password_url': change_password_url,
                    },
                    html_template='mtp_auth/create_new_password.html',
                    anymail_tags=['new-password'],
                )
                return Response(status=status.HTTP_204_NO_CONTENT)
            else:
                password = generate_new_password()
                if not password:
                    logger.error('Password could not be generated; have validators changed?')
                    return self.failure_response('generic')

                user.set_password(password)
                user.save()

                send_email(
                    user.email, 'mtp_auth/reset_password.txt',
                    capfirst(gettext('Your new %(service_name)s password') % {
                        'service_name': service_name,
                    }),
                    context={
                        'service_name': service_name,
                        'username': user.username,
                        'password': password,
                    },
                    html_template='mtp_auth/reset_password.html',
                    anymail_tags=['reset-password'],
                )

                return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return self.failure_response(serializer.errors)


class AccountRequestViewSet(viewsets.ModelViewSet):
    queryset = AccountRequest.objects.none()
    permission_classes = (AccountRequestPremissions,)
    serializer_class = AccountRequestSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return super().get_queryset()
        roles = Role.objects.get_roles_for_user(user)
        queryset = AccountRequest.objects.filter(role__in=roles)
        prisons = list(PrisonUserMapping.objects.get_prison_set_for_user(user).values_list('pk', flat=True))
        if prisons:
            queryset = queryset.filter(prison__in=prisons)
        return queryset

    def perform_create(self, serializer):
        username = serializer.validated_data['username']
        try:
            user = User.objects.get_by_natural_key(username)
            if user.is_superuser:
                raise RestValidationError({
                    api_settings.NON_FIELD_ERRORS_KEY: _(
                        'Super users cannot be edited'
                    )
                })
            roles = Role.objects.get_roles_for_user(user)
            changing_role = self.request.data.get('change-role', '').lower() == 'true'
            if roles and not changing_role:
                raise RestValidationError({
                    '__mtp__': {
                        'condition': 'user-exists',
                        'roles': [
                            {
                                'role': role.name,
                                'application': role.application.name,
                                'login_url': role.login_url,
                            }
                            for role in roles
                        ]
                    },
                    api_settings.NON_FIELD_ERRORS_KEY: _(
                        'This username already exists'
                    ),
                })
            # copy user details that shouldn't change
            for key in ('first_name', 'last_name', 'email'):
                serializer.validated_data[key] = getattr(user, key)
        except User.DoesNotExist:
            pass
        super().perform_create(serializer)

    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user_admin = request.data.get('user_admin', '').lower() == 'true'
        try:
            user = User.objects.get_by_natural_key(instance.username)
            if request.user.pk == user.pk:
                raise RestValidationError({
                    api_settings.NON_FIELD_ERRORS_KEY: _(
                        'You cannot confirm changes to yourself'
                    )
                })
            if user.is_superuser:
                raise RestValidationError({
                    api_settings.NON_FIELD_ERRORS_KEY: _(
                        'Super users cannot be edited'
                    )
                })
            # inactive users get re-activated
            user.is_active = True
            user.save()
            # existing non-superadmins have their prisons, applications and groups replaced
            user.groups.clear()
            PrisonUserMapping.objects.filter(user=user).delete()
            ApplicationUserMapping.objects.filter(user=user).delete()
            user_existed = True
            password = None
        except User.DoesNotExist:
            user = User.objects.create(
                first_name=instance.first_name,
                last_name=instance.last_name,
                email=instance.email,
                username=instance.username,
            )
            password = generate_new_password()
            user.set_password(password)
            user.save()
            user_existed = False

        role = instance.role
        role.assign_to_user(user)
        if user_admin:
            user.groups.add(Group.objects.get(name='UserAdmin'))
        PrisonUserMapping.objects.assign_prisons_from_user(request.user, user)

        context = {
            'username': user.username,
            'password': password,
            'service_name': role.application.name.lower(),
            'login_url': role.login_url,
        }
        if user_existed:
            context.pop('password')
            send_email(
                user.email, 'mtp_auth/user_moved.txt',
                capfirst(gettext('Your new %(service_name)s account is ready to use') % context),
                context=context, html_template='mtp_auth/user_moved.html',
                anymail_tags=['user-moved'],
            )
        else:
            send_email(
                user.email, 'mtp_auth/new_user.txt',
                capfirst(gettext('Your new %(service_name)s account is ready to use') % context),
                context=context, html_template='mtp_auth/new_user.html',
                anymail_tags=['new-user'],
            )

        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(user).pk,
            object_id=user.pk,
            object_repr=gettext('Accepted account request for %(username)s') % {
                'username': user.username,
            },
            action_flag=CHANGE_LOG_ENTRY,
        )

        instance.delete()
        return Response({})

    def perform_destroy(self, instance):
        context = {
            'service_name': instance.role.application.name.lower(),
        }
        send_email(
            instance.email, 'mtp_auth/account_request_denied.txt',
            capfirst(gettext('Account access for %(service_name)s was denied') % context),
            context=context,
            html_template='mtp_auth/account_request_denied.html',
            anymail_tags=['account-request-denied'],
        )
        LogEntry.objects.log_action(
            user_id=self.request.user.pk,
            content_type_id=get_content_type_for_model(instance).pk,
            object_id=instance.pk,
            object_repr=gettext('Declined account request from %(username)s') % {
                'username': instance.username,
            },
            action_flag=DELETION_LOG_ENTRY,
        )
        super().perform_destroy(instance)


class LoginStatsView(BaseAdminReportView):
    title = _('Staff logins per prison')
    template_name = 'admin/mtp_auth/login/prison-report.html'
    form_class = LoginStatsForm
    required_permissions = ['transaction.view_dashboard']

    @classmethod
    def get_months(cls):
        today = timezone.localtime()
        month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        next_month = month_start.month + 1
        if next_month > 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=next_month)

        current_month_progress = (
            (today.timestamp() - month_start.timestamp()) / (next_month.timestamp() - month_start.timestamp())
        )

        months = []
        while len(months) < 4:
            months.append(month_start)
            month = month_start.month - 1
            if month < 1:
                month_start = month_start.replace(year=month_start.year - 1, month=12)
            else:
                month_start = month_start.replace(month=month)

        return current_month_progress, months

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        current_month_progress, months = self.get_months()
        self.current_month_progress = current_month_progress
        self.months = months

    def get_form_kwargs(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs['months'] = self.months
        return form_kwargs

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        form = context_data['form']

        prisons = self.get_prisons()
        login_counts = self.get_login_counts(form.cleaned_data['application'])

        login_stats = []
        for nomis_id, prison_name in prisons:
            login_stat = {
                'nomis_id': nomis_id,
                'prison_name': prison_name,
            }
            monthly_counts = []
            for month in self.months:
                month_key = date_format(month, 'Y-m')
                month_count = login_counts[(nomis_id, month_key)]
                login_stat[month_key] = month_count
                monthly_counts.append(month_count)
            login_stat['monthly_counts'] = monthly_counts
            login_stats.append(login_stat)

        ordering, reversed_order = form.get_ordering()
        login_stats = sorted(
            login_stats, key=lambda s: s[ordering],
            reverse=reversed_order
        )

        context_data['opts'] = Login._meta
        context_data['form'] = form
        context_data['login_stats'] = login_stats
        return context_data

    def get_prisons(self):
        prisons = Prison.objects \
            .exclude(nomis_id__in=self.excluded_nomis_ids) \
            .order_by('nomis_id') \
            .values_list('nomis_id', 'name')
        prisons = list(prisons)
        prisons.append(('', _('Prison not specified')))
        return prisons

    def get_login_counts(self, application):
        login_count_query = f"""
            WITH users AS (
              SELECT user_id, COUNT(*) AS login_count
              FROM mtp_auth_login
              WHERE application_id = %(application_id)s
                AND date_trunc('month', created AT TIME ZONE '{settings.TIME_ZONE}') = %(month)s
              GROUP BY user_id
            )
            SELECT prison_id, SUM(login_count)::integer AS login_count
            FROM users
            LEFT OUTER JOIN mtp_auth_prisonusermapping ON mtp_auth_prisonusermapping.user_id = users.user_id
            LEFT OUTER JOIN mtp_auth_prisonusermapping_prisons ON
              mtp_auth_prisonusermapping_prisons.prisonusermapping_id = mtp_auth_prisonusermapping.id
            GROUP BY prison_id
        """
        login_counts = collections.defaultdict(int)
        try:
            application = Application.objects.get(client_id=application)
        except Application.DoesNotExist:
            return login_counts
        for i, month in enumerate(self.months):
            if i == 0:
                def scale_func(count):
                    return int(round(count / self.current_month_progress))
            else:
                def scale_func(count):
                    return count
            with connection.cursor() as cursor:
                cursor.execute(login_count_query, {
                    'application_id': application.id,
                    'month': month.date(),
                })
                for nomis_id, login_count in cursor.fetchall():
                    login_counts[(nomis_id, date_format(month, 'Y-m'))] = scale_func(login_count)
        return login_counts
