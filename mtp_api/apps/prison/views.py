from django.utils.dateparse import parse_date
from rest_framework import mixins, viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import ActionsBasedPermissions
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    NomsOpsClientIDPermissions, SendMoneyClientIDPermissions
)
from prison.models import PrisonerLocation, Category, Population
from prison.serializers import (
    PrisonerLocationSerializer, PrisonerValiditySerializer, PrisonSerializer,
    PopulationSerializer, CategorySerializer
)


class PrisonerLocationView(
    mixins.CreateModelMixin, viewsets.GenericViewSet,
):
    queryset = PrisonerLocation.objects.all()

    permission_classes = (
        IsAuthenticated, NomsOpsClientIDPermissions,
        ActionsBasedPermissions
    )
    serializer_class = PrisonerLocationSerializer

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


class PrisonerValidityView(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PrisonerLocation.objects.all()
    permission_classes = (
        IsAuthenticated, SendMoneyClientIDPermissions,
    )
    serializer_class = PrisonerValiditySerializer

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        return queryset.filter(
            prisoner_number=self.request.GET['prisoner_number'],
            prisoner_dob=self.request.GET['prisoner_dob'],
        )

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


class PrisonView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = PrisonSerializer

    def get_queryset(self):
        return (
            PrisonUserMapping.objects.get_prison_set_for_user(self.request.user)
            .order_by('name')
        )


class PopulationView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = PopulationSerializer
    queryset = Population.objects.all()


class CategoryView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
