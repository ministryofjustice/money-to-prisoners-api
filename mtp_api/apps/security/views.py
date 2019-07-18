from django.db.models import Count, Case, When, Value, Q
from django.db.models.fields import BooleanField
from django.shortcuts import get_object_or_404
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import decorators, filters, mixins, status, views, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings

from core.filters import MultipleFieldCharFilter, MultipleValueFilter
from core.permissions import ActionsBasedPermissions
from credit.constants import CREDIT_SOURCE
from credit.views import GetCredits
from disbursement.views import GetDisbursementsView
from mtp_auth.permissions import NomsOpsClientIDPermissions
from prison.models import Prison
from security.models import (
    SenderProfile, PrisonerProfile, RecipientProfile, SavedSearch,
    BankAccount, DebitCardSenderDetails,
)
from security.permissions import SecurityProfilePermissions
from security.serializers import (
    SenderProfileSerializer, PrisonerProfileSerializer, SavedSearchSerializer,
    RecipientProfileSerializer,
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


class MonitorProfileMixin(viewsets.GenericViewSet):
    def get_monitor_object(self):
        return self.get_object()

    @decorators.action(
        methods=['post'], detail=True,
        permission_classes=[IsAuthenticated, NomsOpsClientIDPermissions],
        url_path='monitor', url_name='monitor'
    )
    def monitor(self, request, pk=None):
        obj = self.get_monitor_object()
        obj.monitoring_users.add(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @decorators.action(
        methods=['post'], detail=True,
        permission_classes=[IsAuthenticated, NomsOpsClientIDPermissions],
        url_path='unmonitor', url_name='unmonitor'
    )
    def unmonitor(self, request, pk=None):
        obj = self.get_monitor_object()
        obj.monitoring_users.remove(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SenderProfileListFilter(django_filters.FilterSet):
    sender = MultipleFieldCharFilter(
        field_name=(
            'bank_transfer_details__sender_name',
            'debit_card_details__cardholder_name__name',
            'debit_card_details__sender_email__email',
        ),
        lookup_expr='icontains'
    )
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
    prisoner_count__gte = django_filters.NumberFilter(
        field_name='prisoner_count', lookup_expr='gte'
    )
    prisoner_count__lte = django_filters.NumberFilter(
        field_name='prisoner_count', lookup_expr='lte'
    )

    prison = django_filters.ModelMultipleChoiceFilter(
        field_name='prisons', queryset=Prison.objects.all()
    )
    prison_region = django_filters.CharFilter(field_name='prisons__region')
    prison_population = MultipleValueFilter(field_name='prisons__populations__name')
    prison_category = MultipleValueFilter(field_name='prisons__categories__name')
    prison_count__gte = django_filters.NumberFilter(
        field_name='prison_count', lookup_expr='gte'
    )
    prison_count__lte = django_filters.NumberFilter(
        field_name='prison_count', lookup_expr='lte'
    )

    monitoring = django_filters.BooleanFilter()

    class Meta:
        model = SenderProfile
        fields = {
            'credit_count': ['lte', 'gte'],
            'credit_total': ['lte', 'gte'],
            'modified': ['lt', 'gte'],
        }


class SenderProfileView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, MonitorProfileMixin,
    viewsets.GenericViewSet
):
    queryset = SenderProfile.objects.all().annotate(
        prisoner_count=Count('prisoners', distinct=True),
        prison_count=Count('prisons', distinct=True),
    ).prefetch_related(
        'bank_transfer_details', 'debit_card_details',
    )
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = SenderProfileListFilter
    serializer_class = SenderProfileSerializer
    ordering_param = api_settings.ORDERING_PARAM
    ordering_fields = (
        'prisoner_count', 'prison_count', 'credit_count', 'credit_total',
    )
    default_ordering = ('-prisoner_count',)

    permission_classes = (
        IsAuthenticated, SecurityProfilePermissions, NomsOpsClientIDPermissions
    )

    def get_monitor_object(self):
        profile = self.get_object()
        bank_details = profile.bank_transfer_details.first()
        card_details = profile.debit_card_details.first()
        if bank_details:
            return bank_details.sender_bank_account
        elif card_details:
            return card_details
        return None

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.annotate(
            monitoring=Case(
                When(
                    Q(bank_transfer_details__sender_bank_account__monitoring_users=self.request.user) |
                    Q(debit_card_details__monitoring_users=self.request.user),
                    then=Value(True)
                ),
                default=Value(False),
                output_field=BooleanField()
            )
        )
        return qs


class SenderProfileCreditsView(GetCredits):
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
    sender_count__gte = django_filters.NumberFilter(
        name='sender_count', lookup_expr='gte'
    )
    sender_count__lte = django_filters.NumberFilter(
        name='sender_count', lookup_expr='lte'
    )

    monitoring = django_filters.BooleanFilter()

    class Meta:
        model = PrisonerProfile
        fields = {
            'credit_count': ['lte', 'gte'],
            'credit_total': ['lte', 'gte'],
            'disbursement_count': ['lte', 'gte'],
            'disbursement_total': ['lte', 'gte'],
            'prisoner_number': ['exact'],
            'prisoner_dob': ['exact'],
            'modified': ['lt', 'gte'],
        }


class PrisonerProfileView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, MonitorProfileMixin,
    viewsets.GenericViewSet
):
    queryset = PrisonerProfile.objects.all().annotate(
        sender_count=Count('senders', distinct=True),
        recipient_count=Count('recipients', distinct=True),
    ).prefetch_related(
        'prisons', 'provided_names'
    )
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = PrisonerProfileListFilter
    serializer_class = PrisonerProfileSerializer
    ordering_fields = (
        'sender_count', 'credit_count', 'credit_total',
        'recipient_count', 'disbursement_count', 'disbursement_total',
        'prisoner_name', 'prisoner_number',
    )
    default_ordering = ('-sender_count',)

    permission_classes = (
        IsAuthenticated, SecurityProfilePermissions, NomsOpsClientIDPermissions
    )

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.annotate(
            monitoring=Case(
                When(
                    monitoring_users=self.request.user, then=Value(True)
                ),
                default=Value(False),
                output_field=BooleanField()
            )
        )
        return qs


class PrisonerProfileCreditsView(GetCredits):
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


class PrisonerProfileDisbursementsView(GetDisbursementsView):
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


class RecipientProfileListFilter(django_filters.FilterSet):
    recipient_sort_code = django_filters.CharFilter(
        field_name='bank_transfer_details__recipient_bank_account__sort_code'
    )
    recipient_account_number = django_filters.CharFilter(
        field_name='bank_transfer_details__recipient_bank_account__account_number'
    )
    recipient_roll_number = django_filters.CharFilter(
        field_name='bank_transfer_details__recipient_bank_account__roll_number'
    )

    prisoners = django_filters.ModelMultipleChoiceFilter(
        field_name='prisoners', queryset=PrisonerProfile.objects.all()
    )
    prisoner_count__gte = django_filters.NumberFilter(
        field_name='prisoner_count', lookup_expr='gte'
    )
    prisoner_count__lte = django_filters.NumberFilter(
        field_name='prisoner_count', lookup_expr='lte'
    )

    prison = django_filters.ModelMultipleChoiceFilter(
        field_name='prisons', queryset=Prison.objects.all()
    )
    prison_region = django_filters.CharFilter(field_name='prisons__region')
    prison_population = MultipleValueFilter(field_name='prisons__populations__name')
    prison_category = MultipleValueFilter(field_name='prisons__categories__name')
    prison_count__gte = django_filters.NumberFilter(
        field_name='prison_count', lookup_expr='gte'
    )
    prison_count__lte = django_filters.NumberFilter(
        field_name='prison_count', lookup_expr='lte'
    )

    monitoring = django_filters.BooleanFilter()

    class Meta:
        model = RecipientProfile
        fields = {
            'disbursement_count': ['lte', 'gte'],
            'disbursement_total': ['lte', 'gte'],
            'modified': ['lt', 'gte'],
        }


class RecipientProfileView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, MonitorProfileMixin,
    viewsets.GenericViewSet
):
    queryset = RecipientProfile.objects.exclude(
        bank_transfer_details__isnull=True
    ).annotate(
        prisoner_count=Count('prisoners', distinct=True),
        prison_count=Count('prisons', distinct=True),
    ).prefetch_related(
        'bank_transfer_details'
    )
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = RecipientProfileListFilter
    serializer_class = RecipientProfileSerializer
    ordering_param = api_settings.ORDERING_PARAM
    ordering_fields = (
        'prisoner_count', 'prison_count', 'disbursement_count', 'disbursement_total',
    )
    default_ordering = ('-prisoner_count',)

    permission_classes = (
        IsAuthenticated, SecurityProfilePermissions, NomsOpsClientIDPermissions
    )

    def get_monitor_object(self):
        obj = super().get_object()
        bank_details = obj.bank_transfer_details.first()
        if bank_details:
            return bank_details.recipient_bank_account

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.annotate(
            monitoring=Case(
                When(
                    bank_transfer_details__recipient_bank_account__monitoring_users=self.request.user,
                    then=Value(True)
                ),
                default=Value(False),
                output_field=BooleanField()
            )
        )
        return qs


class RecipientProfileDisbursementsView(GetDisbursementsView):
    def list(self, request, recipient_pk=None):
        recipient = get_object_or_404(RecipientProfile, pk=recipient_pk)
        queryset = self.get_queryset().filter(recipient_profile=recipient)
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class MonitoredView(views.APIView):
    # this will return monitored profiles once needed by the security tool
    permission_classes = (IsAuthenticated, NomsOpsClientIDPermissions)

    def get(self, request):
        return Response({
            'count': (
                BankAccount.objects.filter(monitoring_users=request.user).count() +
                DebitCardSenderDetails.objects.filter(monitoring_users=request.user).count() +
                PrisonerProfile.objects.filter(monitoring_users=request.user).count()
            ),
        })


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
