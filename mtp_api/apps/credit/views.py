from functools import reduce
import logging
import re

from django.contrib.auth import get_user_model
from django.db import models, transaction
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from django_filters.widgets import BooleanWidget
from django.utils import timezone
from rest_framework import generics, mixins, status as drf_status, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.filters import (
    annotate_filter,
    BaseFilterSet,
    BlankStringFilter,
    IsoDateTimeFilter,
    LogNomsOpsSearchDjangoFilterBackend,
    MultipleFieldCharFilter,
    MultipleValueFilter,
    PostcodeFilter,
    SafeOrderingFilter,
    SplitTextInMultipleFieldsFilter,
    StatusChoiceFilter,
)
from core.models import TruncUtcDate
from core.permissions import ActionsBasedPermissions
from credit.constants import CreditResolution, CreditStatus, CreditSource, LogAction
from credit.models import Credit, Comment, ProcessingBatch, PrivateEstateBatch
from credit.permissions import CreditPermissions, PrivateEstateBatchPermissions
from credit.serializers import (
    CommentSerializer,
    CreditedOnlyCreditSerializer,
    CreditSerializer,
    CreditsGroupedByCreditedSerializer,
    IdsCreditSerializer,
    PrivateEstateBatchCreditSerializer,
    PrivateEstateBatchSerializer,
    ProcessingBatchSerializer,
    SecurityCreditCheckSerializer,
    SecurityCreditSerializer,
)
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    CashbookClientIDPermissions, BankAdminClientIDPermissions, NomsOpsClientIDPermissions,
    CASHBOOK_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
    get_client_permissions_class,
)
from prison.models import Prison

User = get_user_model()
logger = logging.getLogger('mtp')


class CreditTextSearchFilter(django_filters.CharFilter):
    """
    Filters credits using a text search.
    Works by splitting the input into words and matches any credits
    that have *all* of these words in *any* of these fields:
    - prisoner_name
    - prisoner_number
    - sender_name
    - amount (input is expected as £nn.nn but is reformatted for search)
    """
    fields = [
        'prisoner_name', 'prisoner_number', 'sender_name', 'amount',
        'payment__uuid'
    ]

    def filter(self, qs, value):
        if not value:
            return qs

        re_amount = re.compile(r'^£?(\d+(?:\.\d\d)?)$')

        def get_field_filter(field, word):
            if field == 'amount':
                # for amount fields, only do a search if the input looks
                # like a currency value (£n.nn), this is reformatted by
                # stripping the £ and . to turn it into integer pence
                matches = re_amount.match(word)
                if not matches:
                    return None
                search_term = matches.group(1)
                amount = search_term.replace('.', '')
                # exact match if amount fully specified e.g. £5.00,
                # startswith if not e.g. £5
                if '.' in search_term:
                    return models.Q(**{'%s' % field: amount})
                else:
                    return models.Q(**{'%s__startswith' % field: amount})
            elif field == 'sender_name':
                return (
                    models.Q(**{'transaction__sender_name__icontains': word})
                    | models.Q(**{'payment__cardholder_name__icontains': word})
                )
            elif field == 'payment__uuid':
                if len(word) == 8:
                    return models.Q(**{'%s__startswith' % field: word})
                return None

            return models.Q(**{'%s__icontains' % field: word})

        for value_word in value.split():
            qs = qs.filter(
                reduce(
                    lambda a, b: a | b,
                    filter(bool, [get_field_filter(field, value_word) for field in self.fields])
                )
            )
        return qs


class ValidCreditFilter(django_filters.BooleanFilter):
    def filter(self, queryset, value):
        valid_query = (
            Credit.STATUS_LOOKUP[CreditStatus.credit_pending.value] |
            Credit.STATUS_LOOKUP[CreditStatus.credited.value]
        )
        if value:
            return queryset.filter(valid_query)
        else:
            return queryset.filter(~valid_query)


class CreditSourceFilter(django_filters.ChoiceFilter):
    def __init__(self, *args, **kwargs):
        kwargs['choices'] = CreditSource.choices
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value == CreditSource.bank_transfer.value:
            qs = qs.filter(transaction__isnull=False)
        elif value == CreditSource.online.value:
            qs = qs.filter(payment__isnull=False)
        elif value == CreditSource.unknown.value:
            qs = qs.filter(payment__isnull=True, transaction__isnull=True)
        return qs


class MonitoredProfileFilter(django_filters.BooleanFilter):
    def filter(self, qs, value):
        if value:
            return qs.monitored_by(self.parent.request.user)
        return qs


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass


class CreditListFilter(BaseFilterSet):
    status = StatusChoiceFilter(choices=CreditStatus.choices)
    user = django_filters.ModelChoiceFilter(field_name='owner', queryset=User.objects.all())
    valid = ValidCreditFilter(widget=BooleanWidget)

    prisoner_name = django_filters.CharFilter(field_name='prisoner_name', lookup_expr='icontains')
    prison = django_filters.ModelMultipleChoiceFilter(queryset=Prison.objects.all())
    prison__isnull = django_filters.BooleanFilter(field_name='prison', lookup_expr='isnull')
    prison_region = django_filters.CharFilter(field_name='prison__region')
    prison_category = MultipleValueFilter(field_name='prison__categories__name')
    prison_population = MultipleValueFilter(field_name='prison__populations__name')

    simple_search = SplitTextInMultipleFieldsFilter(
        field_names=(
            'transaction__sender_name',
            'payment__cardholder_name',
            'payment__email',
            'prisoner_number',
        ),
        lookup_expr='icontains',
    )
    search = CreditTextSearchFilter()

    sender_name = MultipleFieldCharFilter(
        field_name=('transaction__sender_name', 'payment__cardholder_name',),
        lookup_expr='icontains'
    )
    sender_sort_code = django_filters.CharFilter(field_name='transaction__sender_sort_code')
    sender_account_number = django_filters.CharFilter(field_name='transaction__sender_account_number')
    sender_roll_number = django_filters.CharFilter(field_name='transaction__sender_roll_number')
    sender_name__isblank = BlankStringFilter(field_name='transaction__sender_name')
    sender_sort_code__isblank = BlankStringFilter(field_name='transaction__sender_sort_code')
    sender_account_number__isblank = BlankStringFilter(field_name='transaction__sender_account_number')
    sender_roll_number__isblank = BlankStringFilter(field_name='transaction__sender_roll_number')

    security_check__isnull = django_filters.BooleanFilter(field_name='security_check', lookup_expr='isnull')
    security_check__actioned_by__isnull = django_filters.BooleanFilter(
        field_name='security_check__actioned_by', lookup_expr='isnull'
    )

    card_expiry_date = django_filters.CharFilter(field_name='payment__card_expiry_date')
    card_number_first_digits = django_filters.CharFilter(field_name='payment__card_number_first_digits')
    card_number_last_digits = django_filters.CharFilter(field_name='payment__card_number_last_digits')
    sender_email = django_filters.CharFilter(field_name='payment__email', lookup_expr='icontains')
    sender_postcode = PostcodeFilter(field_name='payment__billing_address__postcode')
    sender_ip_address = django_filters.CharFilter(field_name='payment__ip_address')

    payment_reference = django_filters.CharFilter(field_name='payment__uuid', lookup_expr='startswith')

    exclude_credit__in = NumberInFilter(field_name='id', lookup_expr='in', exclude=True)

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

    received_at__lt = IsoDateTimeFilter(
        field_name='received_at', lookup_expr='lt'
    )
    received_at__gte = IsoDateTimeFilter(
        field_name='received_at', lookup_expr='gte'
    )
    source = CreditSourceFilter()
    pk = MultipleValueFilter(field_name='pk')
    logged_at__lt = annotate_filter(
        IsoDateTimeFilter(field_name='logged_at', lookup_expr='lt'),
        {'logged_at': TruncUtcDate('log__created')}
    )
    logged_at__gte = annotate_filter(
        IsoDateTimeFilter(field_name='logged_at', lookup_expr='gte'),
        {'logged_at': TruncUtcDate('log__created')}
    )
    monitored = MonitoredProfileFilter()

    class Meta:
        model = Credit
        fields = {
            'prisoner_number': ['exact'],
            'amount': ['exact', 'lte', 'gte'],
            'reviewed': ['exact'],
            'resolution': ['exact'],
            'log__action': ['exact'],
        }


class CreditViewMixin:
    root_queryset = Credit.objects

    def get_queryset(self):
        queryset = self.root_queryset.all()
        cashbook_client = self.request.auth.application.client_id == CASHBOOK_OAUTH_CLIENT_ID

        if self.request.user.has_perm('credit.view_any_credit') and not cashbook_client:
            return queryset

        if cashbook_client:
            # must match bank admin UTC date boundary
            queryset = queryset.filter(
                received_at__utcdate__lt=timezone.now().date()
            )

        return queryset.filter(
            prison__in=PrisonUserMapping.objects.get_prison_set_for_user(self.request.user)
        )


class GetCredits(CreditViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    filter_backends = (LogNomsOpsSearchDjangoFilterBackend, SafeOrderingFilter)
    filterset_class = CreditListFilter
    ordering_fields = ('created', 'received_at', 'amount',
                       'prisoner_number', 'prisoner_name')
    action = 'list'

    permission_classes = (
        IsAuthenticated, CreditPermissions, get_client_permissions_class(
            CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
            BANK_ADMIN_OAUTH_CLIENT_ID
        )
    )

    def get_queryset(self, include_checks=False, only_completed=False):
        q = super().get_queryset().select_related('transaction').select_related('payment__batch')
        if include_checks:
            q = q.select_related('security_check')
        if only_completed:
            if self.root_queryset != Credit.objects_all:
                logger.warning('only_completed is only meaningful when using Credit.objects_all')
            q = q.exclude(
                resolution__in=(
                    CreditResolution.initial.value,
                    CreditResolution.failed.value,
                )
            )
        return q

    def get_serializer_class(self):
        if self.request.user.has_perm('security.view_check'):
            return SecurityCreditCheckSerializer
        if self.request.user.has_perm(
            'transaction.view_bank_details_transaction'
        ):
            return SecurityCreditSerializer
        else:
            return CreditSerializer


class CreditsGroupedByCreditedList(CreditViewMixin, generics.ListAPIView):
    serializer_class = CreditsGroupedByCreditedSerializer
    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        CreditPermissions
    )
    filter_backends = (DjangoFilterBackend,)
    filterset_class = CreditListFilter
    action = 'list'

    def get_queryset(self):
        return super().get_queryset().filter(
            Credit.STATUS_LOOKUP[CreditStatus.credited.value],
            log__action=LogAction.credited,
        )

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        queryset = queryset.annotate(logged_at=TruncUtcDate('log__created'))
        queryset = queryset.values('logged_at', 'owner').annotate(
            count=models.Count('*'), total=models.Sum('amount'),
            comment_count=models.Count('comments')
        ).order_by('-logged_at')

        return queryset


class CreditCredits(CreditViewMixin, APIView):
    serializer_class = CreditedOnlyCreditSerializer
    action = 'credit'
    actions = {'post': 'credit'}

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        CreditPermissions
    )

    def get_serializer(self, *args, **kwargs):
        kwargs['context'] = {
            'request': self.request,
            'format': self.format_kwarg,
            'view': self
        }
        return self.serializer_class(*args, **kwargs)

    def post(self, request, format=None):
        deserialized = self.get_serializer(data=request.data, many=True)
        deserialized.is_valid(raise_exception=True)

        conflict_ids = []
        with transaction.atomic():
            for credit_update in deserialized.data:
                if credit_update['credited']:
                    credits = Credit.objects.credit_pending().filter(
                        pk=credit_update['id']
                    ).select_for_update()
                    if len(credits):
                        credits.first().credit_prisoner(
                            request.user, credit_update.get('nomis_transaction_id')
                        )
                    else:
                        conflict_ids.append(credit_update['id'])

        if conflict_ids:
            return Response(
                data={
                    'errors': [
                        {
                            'msg': 'Some credits were not in a valid state for this operation.',
                            'ids': conflict_ids,
                        }
                    ]
                },
                status=drf_status.HTTP_200_OK
            )
        else:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)


class SetManualCredits(CreditViewMixin, APIView):
    serializer_class = IdsCreditSerializer
    action = 'credit'
    actions = {'post': 'credit'}

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        CreditPermissions
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

        credit_ids = deserialized.data.get('credit_ids', [])
        with transaction.atomic():
            conflict_ids = Credit.objects.set_manual(
                self.get_queryset(),
                credit_ids,
                request.user
            )

        if conflict_ids:
            return Response(
                data={
                    'errors': [
                        {
                            'msg': 'Some credits were not in a valid state for this operation.',
                            'ids': conflict_ids,
                        }
                    ]
                },
                status=drf_status.HTTP_200_OK
            )
        else:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)


class ReviewCredits(CreditViewMixin, APIView):
    serializer_class = IdsCreditSerializer
    action = 'review'
    actions = {'post': 'review'}

    permission_classes = (
        IsAuthenticated, NomsOpsClientIDPermissions,
        CreditPermissions
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

        credit_ids = deserialized.data.get('credit_ids', [])
        Credit.objects.review(credit_ids, request.user)

        return Response(status=drf_status.HTTP_204_NO_CONTENT)


class CommentView(
    mixins.CreateModelMixin, viewsets.GenericViewSet
):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions, NomsOpsClientIDPermissions
    )

    def get_serializer(self, *args, **kwargs):
        many = kwargs.pop('many', True)
        return super().get_serializer(many=many, *args, **kwargs)


class ProcessingBatchView(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    queryset = ProcessingBatch.objects.all()
    serializer_class = ProcessingBatchSerializer

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions, CashbookClientIDPermissions
    )

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset.all().order_by('-id')
        return self.queryset.filter(user=self.request.user).order_by('-id')


class PrivateEstateBatchFilter(BaseFilterSet):
    class Meta:
        model = PrivateEstateBatch
        fields = {
            'date': ['exact', 'gte', 'lt'],
            'prison': ['exact'],
        }


class PrivateEstateBatchView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
    viewsets.GenericViewSet
):
    queryset = PrivateEstateBatch.objects.all()
    serializer_class = PrivateEstateBatchSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = PrivateEstateBatchFilter

    permission_classes = (
        IsAuthenticated, PrivateEstateBatchPermissions, BankAdminClientIDPermissions,
    )

    lookup_url_kwarg = 'ref'
    lookup_value_regex = r'[A-Za-z0-9]{3}/\d\d\d\d-\d\d-\d\d'

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        prison, date = self.kwargs[self.lookup_url_kwarg].split('/', 1)
        obj = get_object_or_404(queryset, prison=prison, date=date)
        self.check_object_permissions(self.request, obj)
        return obj

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        if not partial:
            return Response(status=drf_status.HTTP_405_METHOD_NOT_ALLOWED)
        batch = self.get_object()
        if (request.data or {}).get('credited'):
            with transaction.atomic():
                for credit in batch.credit_set.credit_pending():
                    credit.credit_prisoner(self.request.user, nomis_transaction_id=None)
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(status=drf_status.HTTP_400_BAD_REQUEST)


class PrivateEstateBatchCreditsView(GetCredits):
    permission_classes = (
        IsAuthenticated, CreditPermissions, BankAdminClientIDPermissions,
    )

    def get_serializer_class(self):
        return PrivateEstateBatchCreditSerializer

    def list(self, request, **kwargs):
        prison, date = kwargs['batch_ref'].split('/', 1)
        batch = get_object_or_404(PrivateEstateBatchView.queryset, prison=prison, date=date)

        queryset = self.get_queryset().filter(private_estate_batch=batch)
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
