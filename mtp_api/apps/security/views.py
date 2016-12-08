from django.db.models import Count
import django_filters
from rest_framework import mixins, viewsets, filters
from rest_framework.permissions import IsAuthenticated

from core.filters import MultipleFieldCharFilter
from mtp_auth.permissions import NomsOpsClientIDPermissions
from prison.models import Prison
from .models import SenderProfile, PrisonerProfile
from .permissions import SecurityProfilePermissions
from .serializers import SenderProfileSerializer, PrisonerProfileSerializer


class SenderProfileListFilter(django_filters.FilterSet):
    sender_name = MultipleFieldCharFilter(
        name=('bank_transfer_details__sender_name',
              'debit_card_details__cardholder_name__name',),
        lookup_expr='icontains'
    )
    sender_sort_code = django_filters.CharFilter(
        name='bank_transfer_details__sender_sort_code')
    sender_account_number = django_filters.CharFilter(
        name='bank_transfer_details__sender_account_number')
    sender_roll_number = django_filters.CharFilter(
        name='bank_transfer_details__sender_roll_number')
    card_expiry_date = django_filters.CharFilter(
        name='debit_card_details__card_expiry_date')
    card_number_last_digits = django_filters.CharFilter(
        name='debit_card_details__card_number_last_digits')
    prisoner_count__lte = django_filters.NumberFilter(
        name='prisoner_count', lookup_expr='lte')
    prisoner_count__gte = django_filters.NumberFilter(
        name='prisoner_count', lookup_expr='gte')
    prison = django_filters.ModelMultipleChoiceFilter(
        name='prisoners__prisons', queryset=Prison.objects.all()
    )

    class Meta:
        model = SenderProfile
        fields = {
            'credit_count': ['lte', 'gte'],
            'credit_total': ['lte', 'gte'],
        }


class SenderProfileView(
    mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = SenderProfile.objects.all().annotate(prisoner_count=Count('prisoners'))
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = SenderProfileListFilter
    serializer_class = SenderProfileSerializer

    permission_classes = (
        IsAuthenticated, SecurityProfilePermissions, NomsOpsClientIDPermissions
    )


class PrisonerProfileListFilter(django_filters.FilterSet):
    prisoner_name = django_filters.CharFilter(name='prisoner_name', lookup_expr='icontains')
    prison = django_filters.ModelMultipleChoiceFilter(
        name='prisons', queryset=Prison.objects.all()
    )
    sender_count__lte = django_filters.NumberFilter(
        name='sender_count', lookup_expr='lte')
    sender_count__gte = django_filters.NumberFilter(
        name='sender_count', lookup_expr='gte')

    class Meta:
        model = PrisonerProfile
        fields = {
            'prisoner_number': ['exact'],
            'prisoner_dob': ['exact'],
            'credit_count': ['lte', 'gte'],
            'credit_total': ['lte', 'gte'],
            'senders': ['exact'],
        }


class PrisonerProfileView(
    mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = PrisonerProfile.objects.all().annotate(sender_count=Count('senders'))
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = PrisonerProfileListFilter
    serializer_class = PrisonerProfileSerializer

    permission_classes = (
        IsAuthenticated, SecurityProfilePermissions, NomsOpsClientIDPermissions
    )
