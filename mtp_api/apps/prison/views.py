import logging

from django.contrib import messages
from django.db import models, transaction
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.utils.translation import gettext, gettext_lazy as _
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
from prison.forms import PrisonerBalanceUploadForm
from prison.models import PrisonerLocation, Category, Population, Prison, PrisonerBalance
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


class PrisonerBalanceUploadView(AdminViewMixin, FormView):
    title = _('Prisoner balance upload')
    form_class = PrisonerBalanceUploadForm
    template_name = 'admin/prison/prisonerbalance/upload.html'
    success_url = reverse_lazy('admin:prison_prisonerbalance_changelist')
    required_permissions = [
        'prison.add_prisonerbalance', 'prison.change_prisonerbalance', 'prison.delete_prisonerbalance',
    ]

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['opts'] = PrisonerBalance._meta
        return context_data

    def form_valid(self, form):
        result = form.save()
        messages.success(self.request, (
            gettext('Deleted %(count)d balances.') % {'count': result['deleted']} + ' ' +
            gettext('Saved %(count)d balances.') % {'count': result['created']}
        ))
        # prisoner balances are tied to prisoners by number AND prison
        # either prisoner balances OR prisoner locations can be stale (depends on when files are generated and imported)
        # so both need to link to prison and we should not automatically choose the prison being uploaded
        chosen_prison = form.cleaned_data['prison']
        # but since the wrong prison can be accidentally chosen, an error should show if this might have happened
        likely_prison = self.prison_based_on_known_locations(chosen_prison)
        if likely_prison and likely_prison != chosen_prison:
            messages.error(self.request, gettext(
                'File was uploaded for %(chosen_prison)s, '
                'but database suggests that most prisoners are likely at %(likely_prison)s.'
            ) % {
                'chosen_prison': chosen_prison,
                'likely_prison': likely_prison,
            } + ' ' + gettext('Was the right prison selected?'))
        return super().form_valid(form)

    @classmethod
    def prison_based_on_known_locations(cls, chosen_prison):
        # prisoner numbers that were just uploaded
        uploaded_prisoner_numbers = PrisonerBalance.objects.filter(prison=chosen_prison) \
            .values('prisoner_number')
        # their prisons as determined by known locations
        likely_prisons = PrisonerLocation.objects.filter(prisoner_number__in=uploaded_prisoner_numbers) \
            .order_by() \
            .values('prison') \
            .annotate(count=models.Count('*')) \
            .values('prison', 'count') \
            .order_by('-count')
        # prison that most uploaded prisoners are in
        likely_prison = likely_prisons.first()
        if likely_prison:
            return Prison.objects.get(pk=likely_prison['prison'])
