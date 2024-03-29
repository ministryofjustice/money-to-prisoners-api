from django.db.transaction import atomic
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.filters import (
    annotate_filter,
    BaseFilterSet,
    IsoDateTimeFilter,
    MultipleValueFilter,
    PostcodeFilter,
    SafeOrderingFilter,
    SplitTextInMultipleFieldsFilter,
)
from core.models import TruncUtcDate
from core.permissions import ActionsBasedViewPermissions
from disbursement import InvalidDisbursementStateException
from disbursement.constants import DisbursementResolution
from disbursement.models import Disbursement, Comment
from disbursement.serializers import (
    DisbursementSerializer, DisbursementIdsSerializer,
    DisbursementConfirmationSerializer, CommentSerializer,
)
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    CashbookClientIDPermissions, BankAdminClientIDPermissions,
    CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
    BANK_ADMIN_OAUTH_CLIENT_ID, get_client_permissions_class,
)
from prison.models import Prison


class MonitoredProfileFilter(django_filters.BooleanFilter):
    def filter(self, qs, value):
        if value:
            return qs.monitored_by(self.parent.request.user)
        return qs


class DisbursementFilter(BaseFilterSet):
    logged_at__lt = annotate_filter(
        IsoDateTimeFilter(field_name='logged_at', lookup_expr='lt'),
        {'logged_at': TruncUtcDate('log__created')}
    )
    logged_at__gte = annotate_filter(
        IsoDateTimeFilter(field_name='logged_at', lookup_expr='gte'),
        {'logged_at': TruncUtcDate('log__created')}
    )
    resolution = MultipleValueFilter(field_name='resolution')

    exclude_amount__endswith = django_filters.CharFilter(
        field_name='amount', lookup_expr='endswith', exclude=True
    )
    exclude_amount__regex = django_filters.CharFilter(
        field_name='amount', lookup_expr='regex', exclude=True
    )
    amount__endswith = django_filters.CharFilter(
        field_name='amount', lookup_expr='endswith'
    )
    amount__regex = django_filters.CharFilter(
        field_name='amount', lookup_expr='regex'
    )

    simple_search = SplitTextInMultipleFieldsFilter(
        field_names=(
            'recipient_first_name',
            'recipient_last_name',
            'prisoner_number',
        ),
        lookup_expr='icontains',
    )

    prisoner_number = django_filters.CharFilter(field_name='prisoner_number', lookup_expr='iexact')
    prisoner_name = django_filters.CharFilter(field_name='prisoner_name', lookup_expr='icontains')

    prison = django_filters.ModelMultipleChoiceFilter(queryset=Prison.objects.all())
    prison_region = django_filters.CharFilter(field_name='prison__region')
    prison_category = MultipleValueFilter(field_name='prison__categories__name')
    prison_population = MultipleValueFilter(field_name='prison__populations__name')

    recipient_name = django_filters.CharFilter(field_name='recipient_name', lookup_expr='icontains')
    recipient_email = django_filters.CharFilter(field_name='recipient_email', lookup_expr='icontains')

    city = django_filters.CharFilter(field_name='city', lookup_expr='iexact')
    postcode = PostcodeFilter(field_name='postcode')

    sort_code = django_filters.CharFilter(field_name='sort_code')
    account_number = django_filters.CharFilter(field_name='account_number')
    roll_number = django_filters.CharFilter(field_name='roll_number')

    invoice_number = django_filters.CharFilter(field_name='invoice_number', lookup_expr='iexact')
    monitored = MonitoredProfileFilter()

    class Meta:
        model = Disbursement
        fields = {
            'created': ['exact', 'lt', 'gte'],
            'log__action': ['exact'],
            'method': ['exact'],
            'amount': ['exact', 'lte', 'gte'],
            'nomis_transaction_id': ['exact'],
            'recipient_is_company': ['exact'],
        }


class DisbursementViewMixin:
    def get_queryset(self):
        queryset = Disbursement.objects.all()
        if getattr(self, 'swagger_fake_view', False):
            return queryset
        if self.request.auth.application.client_id == CASHBOOK_OAUTH_CLIENT_ID:
            return queryset.filter(
                prison__in=PrisonUserMapping.objects.get_prison_set_for_user(self.request.user)
            )
        return queryset


class GetDisbursementsView(
    DisbursementViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    queryset = Disbursement.objects.all().order_by('-id')
    serializer_class = DisbursementSerializer
    filterset_class = DisbursementFilter
    filter_backends = (DjangoFilterBackend, SafeOrderingFilter)
    ordering_fields = ('created', 'amount', 'resolution', 'method', 'recipient_name',
                       'prisoner_number', 'prisoner_name')
    permission_classes = (
        IsAuthenticated, ActionsBasedViewPermissions, get_client_permissions_class(
            CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
            BANK_ADMIN_OAUTH_CLIENT_ID
        )
    )


class DisbursementView(
    mixins.CreateModelMixin, mixins.UpdateModelMixin, GetDisbursementsView
):
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.resolution == DisbursementResolution.pending.value:
            return super().update(request, *args, **kwargs)
        else:
            return Response(
                data={
                    'errors': [{
                        'msg': 'This disbursement can no longer be modified.'
                    }]
                },
                status=status.HTTP_400_BAD_REQUEST
            )


class ResolveDisbursementsView(DisbursementViewMixin, APIView):
    serializer_class = DisbursementIdsSerializer
    action = 'update'
    resolution = NotImplemented

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        ActionsBasedViewPermissions
    )

    def get_serializer(self, *args, **kwargs):
        kwargs['context'] = {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self
        }
        return self.serializer_class(*args, **kwargs)

    def post(self, request, format=None):
        deserialized = self.get_serializer(data=request.data)
        deserialized.is_valid(raise_exception=True)

        disbursement_ids = deserialized.data.get('disbursement_ids', [])
        try:
            Disbursement.objects.update_resolution(
                self.get_queryset(), disbursement_ids, self.resolution, request.user
            )
        except InvalidDisbursementStateException as e:
            return Response(
                data={
                    'errors': [{
                        'msg': 'Some disbursements were not in a valid state for this operation.',
                        'ids': e.conflict_ids,
                    }]
                },
                status=status.HTTP_409_CONFLICT
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class RejectDisbursementsView(ResolveDisbursementsView):
    resolution = DisbursementResolution.rejected.value


class PreConfirmDisbursementsView(ResolveDisbursementsView):
    resolution = DisbursementResolution.preconfirmed.value


class ResetDisbursementsView(ResolveDisbursementsView):
    resolution = DisbursementResolution.pending.value


class SendDisbursementsView(ResolveDisbursementsView):
    resolution = DisbursementResolution.sent.value

    permission_classes = (
        IsAuthenticated, ActionsBasedViewPermissions, BankAdminClientIDPermissions
    )


class ConfirmDisbursementsView(DisbursementViewMixin, APIView):
    serializer_class = DisbursementConfirmationSerializer
    action = 'update'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        ActionsBasedViewPermissions
    )

    def get_serializer(self, *args, **kwargs):
        kwargs['context'] = {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self
        }
        return self.serializer_class(*args, **kwargs)

    @atomic
    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        confirmed_disbursements = {
            d['id']: d.get('nomis_transaction_id') for d in serializer.data
        }
        disbursement_ids = confirmed_disbursements.keys()
        to_update = Disbursement.objects.preconfirmed().filter(
            pk__in=disbursement_ids
        ).select_for_update()

        ids_to_update = [c.id for c in to_update]
        conflict_ids = set(disbursement_ids) - set(ids_to_update)
        if conflict_ids:
            return Response(
                data={
                    'errors': [{
                        'msg': 'Some disbursements were not in a valid state for this operation.',
                        'ids': sorted(conflict_ids)
                    }]
                },
                status=status.HTTP_409_CONFLICT
            )

        for disbursement in to_update:
            disbursement.confirm(
                request.user, confirmed_disbursements[disbursement.id]
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentView(
    mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer

    permission_classes = (
        IsAuthenticated, ActionsBasedViewPermissions, CashbookClientIDPermissions
    )

    def get_serializer(self, *args, **kwargs):
        kwargs.setdefault('many', True)
        return super().get_serializer(*args, **kwargs)
