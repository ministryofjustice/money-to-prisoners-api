from django.db.models import Count
import django_filters
from rest_framework import mixins, viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings

from core.filters import MultipleFieldCharFilter, MultipleValueFilter
from credit.constants import CREDIT_SOURCE
from credit.views import GetCredits
from mtp_auth.permissions import NomsOpsClientIDPermissions
from prison.models import Prison
from .models import SenderProfile, PrisonerProfile
from .permissions import SecurityProfilePermissions
from .serializers import SenderProfileSerializer, PrisonerProfileSerializer


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
        name=('bank_transfer_details__sender_name',
              'debit_card_details__cardholder_name__name',),
        lookup_expr='icontains'
    )

    source = SenderCreditSourceFilter()
    sender_sort_code = django_filters.CharFilter(name='bank_transfer_details__sender_sort_code')
    sender_account_number = django_filters.CharFilter(name='bank_transfer_details__sender_account_number')
    sender_roll_number = django_filters.CharFilter(name='bank_transfer_details__sender_roll_number')
    card_expiry_date = django_filters.CharFilter(name='debit_card_details__card_expiry_date')
    card_number_last_digits = django_filters.CharFilter(name='debit_card_details__card_number_last_digits')
    sender_email = django_filters.CharFilter(name='debit_card_details__sender_email__email', lookup_expr='icontains')

    prisoners = django_filters.ModelMultipleChoiceFilter(name='prisoners', queryset=PrisonerProfile.objects.all())
    prisoner_count__lte = django_filters.NumberFilter(name='prisoner_count', lookup_expr='lte')
    prisoner_count__gte = django_filters.NumberFilter(name='prisoner_count', lookup_expr='gte')

    prison = django_filters.ModelMultipleChoiceFilter(name='prisoners__prisons', queryset=Prison.objects.all())
    prison_region = django_filters.CharFilter(name='prisoners__prisons__region')
    prison_population = MultipleValueFilter(name='prisoners__prisons__populations__name')
    prison_category = MultipleValueFilter(name='prisoners__prisons__categories__name')

    class Meta:
        model = SenderProfile
        fields = {
            'credit_count': ['lte', 'gte'],
            'credit_total': ['lte', 'gte'],
            'modified': ['lt', 'gte'],
        }


class SenderProfileView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = SenderProfile.objects.all().annotate(
        prisoner_count=Count('prisoners'),
        prison_count=Count('prisoners__prisons'),
    )
    filter_backends = (filters.DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = SenderProfileListFilter
    serializer_class = SenderProfileSerializer
    ordering_param = api_settings.ORDERING_PARAM
    ordering_fields = ('prisoner_count', 'credit_count', 'credit_total',)
    default_ordering = ('-prisoner_count',)

    permission_classes = (
        IsAuthenticated, SecurityProfilePermissions, NomsOpsClientIDPermissions
    )


class SenderProfileCreditsView(
    GetCredits
):

    def list(self, request, sender_pk=None):
        sender = SenderProfile.objects.get(pk=sender_pk)
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(sender.credit_filters)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class PrisonerProfileListFilter(django_filters.FilterSet):
    prisoner_name = django_filters.CharFilter(name='prisoner_name', lookup_expr='icontains')

    prison = django_filters.ModelMultipleChoiceFilter(name='prisons', queryset=Prison.objects.all())
    prison_region = django_filters.CharFilter(name='prisons__region')
    prison_population = MultipleValueFilter(name='prisons__populations__name')
    prison_category = MultipleValueFilter(name='prisons__categories__name')

    senders = django_filters.ModelMultipleChoiceFilter(name='senders', queryset=SenderProfile.objects.all())
    sender_count__lte = django_filters.NumberFilter(name='sender_count', lookup_expr='lte')
    sender_count__gte = django_filters.NumberFilter(name='sender_count', lookup_expr='gte')

    class Meta:
        model = PrisonerProfile
        fields = {
            'prisoner_number': ['exact'],
            'prisoner_dob': ['exact'],
            'credit_count': ['lte', 'gte'],
            'credit_total': ['lte', 'gte'],
            'modified': ['lt', 'gte'],
        }


class PrisonerProfileView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = PrisonerProfile.objects.all().annotate(sender_count=Count('senders'))
    filter_backends = (filters.DjangoFilterBackend, filters.OrderingFilter,)
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
        prisoner = PrisonerProfile.objects.get(pk=prisoner_pk)
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(prisoner.credit_filters)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
