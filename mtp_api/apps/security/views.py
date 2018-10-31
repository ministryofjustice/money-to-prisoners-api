from django.db.models.fields import IntegerField
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings

from core.filters import (
    MultipleFieldCharFilter, MultipleValueFilter, annotate_filter
)
from core.permissions import ActionsBasedPermissions
from credit.constants import CREDIT_SOURCE
from credit.views import GetCredits
from mtp_auth.permissions import NomsOpsClientIDPermissions
from prison.models import Prison
from .models import SenderProfile, PrisonerProfile, SavedSearch
from .permissions import SecurityProfilePermissions
from .serializers import (
    SenderProfileSerializer, PrisonerProfileSerializer, SavedSearchSerializer
)


class SenderCreditSourceFilter(django_filters.ChoiceFilter):

    def __init__(self, *args, **kwargs):
        kwargs['choices'] = CREDIT_SOURCE.choices
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value == CREDIT_SOURCE.BANK_TRANSFER:
            qs = qs.filter(bank_transfer_details__isnull=False)
        elif value == CREDIT_SOURCE.ONLINE:
            qs = qs.filter(debit_card_details__isnull=False)
        elif value == CREDIT_SOURCE.UNKNOWN:
            qs = qs.filter(
                debit_card_details__isnull=True,
                bank_transfer_details__isnull=True
            )
        return qs


class SenderProfileListFilter(django_filters.FilterSet):
    sender_name = MultipleFieldCharFilter(
        field_name=(
            'bank_transfer_details__sender_name',
            'debit_card_details__cardholder_name__name',
        ),
        lookup_expr='icontains'
    )

    source = SenderCreditSourceFilter()
    sender_sort_code = django_filters.CharFilter(
        field_name='bank_transfer_details__sender_bank_account__sort_code'
    )
    sender_account_number = django_filters.CharFilter(
        field_name='bank_transfer_details__sender_bank_account__account_number'
    )
    sender_roll_number = django_filters.CharFilter(
        field_name='bank_transfer_details__sender_bank_account__roll_number'
    )
    card_expiry_date = django_filters.CharFilter(
        field_name='debit_card_details__card_expiry_date'
    )
    card_number_last_digits = django_filters.CharFilter(
        field_name='debit_card_details__card_number_last_digits'
    )
    sender_email = django_filters.CharFilter(
        field_name='debit_card_details__sender_email__email', lookup_expr='icontains'
    )
    sender_postcode = django_filters.CharFilter(
        field_name='debit_card_details__postcode', lookup_expr='icontains'
    )

    prisoners = django_filters.ModelMultipleChoiceFilter(
        field_name='prisoners', queryset=PrisonerProfile.objects.all()
    )
    prisoner_count__gte = annotate_filter(
        django_filters.NumberFilter(
            field_name='prisoner_count', lookup_expr='gte'
        ),
        {'prisoner_count': Cast('totals__prisoner_count', IntegerField())}
    )
    prisoner_count__lte = annotate_filter(
        django_filters.NumberFilter(
            field_name='prisoner_count', lookup_expr='lte'
        ),
        {'prisoner_count': Cast('totals__prisoner_count', IntegerField())}
    )

    prison = django_filters.ModelMultipleChoiceFilter(
        field_name='prisons', queryset=Prison.objects.all()
    )
    prison_region = django_filters.CharFilter(field_name='prisons__region')
    prison_population = MultipleValueFilter(field_name='prisons__populations__name')
    prison_category = MultipleValueFilter(field_name='prisons__categories__name')
    prison_count__gte = annotate_filter(
        django_filters.NumberFilter(
            field_name='prison_count', lookup_expr='gte'
        ),
        {'prison_count': Cast('totals__prison_count', IntegerField())}
    )
    prison_count__lte = annotate_filter(
        django_filters.NumberFilter(
            field_name='prison_count', lookup_expr='lte'
        ),
        {'prison_count': Cast('totals__prison_count', IntegerField())}
    )

    credit_count__gte = annotate_filter(
        django_filters.NumberFilter(
            field_name='credit_count', lookup_expr='gte'
        ),
        {'credit_count': Cast('totals__credit_count', IntegerField())}
    )
    credit_count__lte = annotate_filter(
        django_filters.NumberFilter(
            field_name='credit_count', lookup_expr='lte'
        ),
        {'credit_count': Cast('totals__credit_count', IntegerField())}
    )

    class Meta:
        model = SenderProfile
        fields = {
            'modified': ['lt', 'gte'],
            'totals__time_period': ['exact'],
        }


class SenderProfileView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = SenderProfile.objects.all().distinct()
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = SenderProfileListFilter
    serializer_class = SenderProfileSerializer
    ordering_param = api_settings.ORDERING_PARAM
    ordering_fields = ('prisoner_count', 'prison_count', 'credit_count', 'credit_total',)
    default_ordering = ('-prisoner_count',)

    permission_classes = (
        IsAuthenticated, SecurityProfilePermissions, NomsOpsClientIDPermissions
    )


class SenderProfileCreditsView(
    GetCredits
):

    def list(self, request, sender_pk=None):
        sender = get_object_or_404(SenderProfile, pk=sender_pk)
        queryset = self.get_queryset().filter(sender_profile=sender)
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class PrisonerProfileListFilter(django_filters.FilterSet):
    prisoner_name = django_filters.CharFilter(
        name='prisoner_name', lookup_expr='icontains'
    )

    prison = django_filters.ModelMultipleChoiceFilter(
        name='prisons', queryset=Prison.objects.all()
    )
    prison_region = django_filters.CharFilter(name='prisons__region')
    prison_population = MultipleValueFilter(name='prisons__populations__name')
    prison_category = MultipleValueFilter(name='prisons__categories__name')

    senders = django_filters.ModelMultipleChoiceFilter(
        name='senders', queryset=SenderProfile.objects.all()
    )
    sender_count__gte = annotate_filter(
        django_filters.NumberFilter(
            field_name='sender_count', lookup_expr='gte'
        ),
        {'sender_count': Cast('totals__sender_count', IntegerField())}
    )
    sender_count__lte = annotate_filter(
        django_filters.NumberFilter(
            field_name='sender_count', lookup_expr='lte'
        ),
        {'sender_count': Cast('totals__sender_count', IntegerField())}
    )

    class Meta:
        model = PrisonerProfile
        fields = {
            'prisoner_number': ['exact'],
            'prisoner_dob': ['exact'],
            'modified': ['lt', 'gte'],
            'totals__time_period': ['exact'],
        }


class PrisonerProfileView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = PrisonerProfile.objects.all()
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = PrisonerProfileListFilter
    serializer_class = PrisonerProfileSerializer
    ordering_fields = ('sender_count', 'credit_count', 'credit_total', 'prisoner_name', 'prisoner_number')
    default_ordering = ('-sender_count',)

    permission_classes = (
        IsAuthenticated, SecurityProfilePermissions, NomsOpsClientIDPermissions
    )


class PrisonerProfileCreditsView(
    GetCredits
):

    def list(self, request, prisoner_pk=None):
        prisoner = get_object_or_404(PrisonerProfile, pk=prisoner_pk)
        queryset = self.get_queryset().filter(prisoner_profile=prisoner)
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class SavedSearchView(
    mixins.CreateModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin,
    mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = SavedSearch.objects.all()
    serializer_class = SavedSearchSerializer

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions, NomsOpsClientIDPermissions
    )

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)
