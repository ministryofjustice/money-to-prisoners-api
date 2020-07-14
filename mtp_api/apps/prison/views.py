from io import StringIO
import logging

from django.conf import settings
from django.contrib.admin.models import LogEntry, CHANGE as CHANGE_LOG_ENTRY
from django.core.management import call_command
from django.db import transaction
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView
from rest_framework import generics, mixins, viewsets, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.permissions import ActionsBasedPermissions, ActionsBasedViewPermissions
from core.serializers import NullSerializer
from core.views import AdminViewMixin
from credit.signals import credit_prisons_need_updating
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    NomsOpsClientIDPermissions, SendMoneyClientIDPermissions,
    NOMS_OPS_OAUTH_CLIENT_ID, CASHBOOK_OAUTH_CLIENT_ID,
    get_client_permissions_class
)
from prison.forms import LoadOffendersForm
from prison.models import PrisonerLocation, Category, Population, Prison
from prison.serializers import (
    PrisonerLocationSerializer,
    PrisonerValiditySerializer,
    PrisonerAccountBalanceSerializer,
    PrisonSerializer, PopulationSerializer, CategorySerializer,
)
from security.signals import prisoner_profile_current_prisons_need_updating

logger = logging.getLogger('mtp')


class PrisonerLocationView(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = PrisonerLocation.objects.all().filter(active=True)

    permission_classes = (
        IsAuthenticated, ActionsBasedViewPermissions,
        get_client_permissions_class(
            NOMS_OPS_OAUTH_CLIENT_ID, CASHBOOK_OAUTH_CLIENT_ID)
    )
    serializer_class = PrisonerLocationSerializer
    lookup_field = 'prisoner_number'
    lookup_url_kwarg = 'prisoner_number'
    lookup_value_regex = '[A-Za-z]{1}[0-9]{4}[A-Za-z]{2}'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if obj.prison not in PrisonUserMapping.objects.get_prison_set_for_user(
            self.request.user
        ):
            self.permission_denied(
                request,
                message=_(
                    'Cannot retrieve details for this prisoner as they are not '
                    'in a prison that you manage.'
                )
            )


class DeleteOldPrisonerLocationsView(generics.GenericAPIView):
    queryset = PrisonerLocation.objects.all()
    action = 'destroy'
    serializer_class = NullSerializer

    permission_classes = (
        IsAuthenticated, NomsOpsClientIDPermissions,
        ActionsBasedPermissions
    )

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.get_queryset().filter(active=True).delete()
        self.get_queryset().filter(active=False).update(active=True)
        credit_prisons_need_updating.send(sender=PrisonerLocation)
        prisoner_profile_current_prisons_need_updating.send(sender=PrisonerLocation)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeleteInactivePrisonerLocationsView(generics.GenericAPIView):
    queryset = PrisonerLocation.objects.filter(active=False)
    action = 'destroy'
    serializer_class = NullSerializer

    permission_classes = (
        IsAuthenticated, NomsOpsClientIDPermissions,
        ActionsBasedPermissions
    )

    def post(self, request, *args, **kwargs):
        self.get_queryset().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PrisonerValidityView(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PrisonerLocation.objects.filter(active=True)
    permission_classes = (
        IsAuthenticated, SendMoneyClientIDPermissions,
    )
    serializer_class = PrisonerValiditySerializer

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        filters = {
            'prisoner_number': self.request.GET['prisoner_number'],
            'prisoner_dob': self.request.GET['prisoner_dob'],
        }
        prisons = set(filter(None, self.request.GET.get('prisons', '').split(',')))
        if prisons:
            filters['prison__nomis_id__in'] = prisons
        return queryset.filter(**filters)

    def list(self, request, *args, **kwargs):
        prisoner_number = self.request.GET.get('prisoner_number', '')
        prisoner_dob = self.request.GET.get('prisoner_dob', '')
        try:
            prisoner_dob = parse_date(prisoner_dob)
        except ValueError:
            prisoner_dob = None
        if not prisoner_number or not prisoner_dob:
            return Response(data={'errors': "'prisoner_number' and 'prisoner_dob' "
                                            'fields are required'},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().list(request, *args, **kwargs)


class PrisonerAccountBalanceView(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PrisonerLocation.objects.filter(active=True)
    permission_classes = (
        IsAuthenticated, SendMoneyClientIDPermissions,
    )
    serializer_class = PrisonerAccountBalanceSerializer
    lookup_field = 'prisoner_number'
    lookup_url_kwarg = 'prisoner_number'
    lookup_value_regex = '[A-Za-z][0-9]{4}[A-Za-z]{2}'


class PrisonView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    serializer_class = PrisonSerializer
    queryset = Prison.objects.all()

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.request.GET.get('exclude_empty_prisons', '').lower() == 'true':
            queryset = queryset.filter(nomis_id__in=PrisonerLocation.objects.values('prison'))
        return queryset


class PopulationView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = PopulationSerializer
    queryset = Population.objects.all()


class CategoryView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = CategorySerializer
    queryset = Category.objects.all()


class LoadOffendersView(AdminViewMixin, FormView):
    """
    Load offenders from Single Offender ID service
    """
    title = _('Load offenders')
    form_class = LoadOffendersForm
    template_name = 'admin/prison/prisonerlocation/load-offenders.html'
    success_url = reverse_lazy('admin:prison_prisonerlocation_changelist')
    superuser_required = True

    def get_context_data(self, **kwargs):
        available = (
            settings.OFFENDER_API_URL and
            settings.OFFENDER_API_CLIENT_ID and settings.OFFENDER_API_CLIENT_SECRET
        )
        return super().get_context_data(opts=PrisonerLocation._meta, available=available, **kwargs)

    def form_valid(self, form):
        output = StringIO()
        call_command('load_prisoner_locations', no_color=True, stdout=output, stderr=output, verbosity=2,
                     modified_only=form.cleaned_data['modified_only'])
        output.seek(0)
        command_output = output.read()

        LogEntry.objects.log_action(
            user_id=self.request.user.pk,
            content_type_id=None, object_id=None,
            object_repr=_('Offender locations loaded from Single Offender ID'),
            action_flag=CHANGE_LOG_ENTRY,
        )
        logger.info('User "%(username)s" loaded offender locations from Single Offender ID' % {
            'username': self.request.user.username,
        })
        logger.debug(command_output)

        return self.render_to_response(self.get_context_data(
            form=form,
            command_output=command_output,
        ))
