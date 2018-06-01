from functools import reduce
import logging
import re

from django.contrib.auth import get_user_model
from django.db import models, transaction
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from rest_framework import generics, mixins, status as drf_status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.filters import (
    BlankStringFilter, StatusChoiceFilter, IsoDateTimeFilter,
    MultipleFieldCharFilter, SafeOrderingFilter, MultipleValueFilter,
    annotate_filter
)
from core.models import TruncUtcDate
from core.permissions import ActionsBasedPermissions
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    CashbookClientIDPermissions, NomsOpsClientIDPermissions,
    get_client_permissions_class, CASHBOOK_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID
)
from prison.models import Prison
from .constants import CREDIT_STATUS, CREDIT_SOURCE, LOG_ACTIONS
from .models import Credit, Comment, ProcessingBatch
from .permissions import CreditPermissions
from .serializers import (
    CreditSerializer, SecurityCreditSerializer, CreditedOnlyCreditSerializer,
    IdsCreditSerializer, CommentSerializer, ProcessingBatchSerializer,
    CreditsGroupedByCreditedSerializer
)

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
    fields = ['prisoner_name', 'prisoner_number', 'sender_name', 'amount']

    def filter(self, qs, value):
        if not value:
            return qs

        re_amount = re.compile(r'^£?(\d+(?:\.\d\d)?)$')

        for word in value.split():
            def get_field_filter(field):
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

                return models.Q(**{'%s__icontains' % field: word})

            qs = qs.filter(
                reduce(
                    lambda a, b: a | b,
                    filter(bool, map(get_field_filter, self.fields))
                )
            )
        return qs


class ValidCreditFilter(django_filters.BooleanFilter):
    def filter(self, queryset, value):
        valid_query = (
            Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDIT_PENDING] |
            Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED]
        )
        if value:
            return queryset.filter(valid_query)
        else:
            return queryset.filter(~valid_query)


class CreditSourceFilter(django_filters.ChoiceFilter):

    def __init__(self, *args, **kwargs):
        kwargs['choices'] = CREDIT_SOURCE.choices
        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if value == CREDIT_SOURCE.BANK_TRANSFER:
            qs = qs.filter(transaction__isnull=False)
        elif value == CREDIT_SOURCE.ONLINE:
            qs = qs.filter(payment__isnull=False)
        elif value == CREDIT_SOURCE.UNKNOWN:
            qs = qs.filter(payment__isnull=True, transaction__isnull=True)
        return qs


class PostcodeFilter(django_filters.CharFilter):
    def __init__(self, **kwargs):
        kwargs['lookup_expr'] = 'iregex'
        super().__init__(**kwargs)

    def filter(self, qs, value):
        value = re.sub(r'[^0-9A-Za-z]+', '', value)
        value = r'\s*'.join(value)
        return super().filter(qs, value)


class CreditListFilter(django_filters.FilterSet):
    status = StatusChoiceFilter(choices=CREDIT_STATUS.choices)
    user = django_filters.ModelChoiceFilter(field_name='owner', queryset=User.objects.all())
    valid = ValidCreditFilter(widget=django_filters.widgets.BooleanWidget)

    prisoner_name = django_filters.CharFilter(field_name='prisoner_name', lookup_expr='icontains')
    prison = django_filters.ModelMultipleChoiceFilter(queryset=Prison.objects.all())
    prison__isnull = django_filters.BooleanFilter(field_name='prison', lookup_expr='isnull')
    prison_region = django_filters.CharFilter(field_name='prison__region')
    prison_category = MultipleValueFilter(field_name='prison__categories__name')
    prison_population = MultipleValueFilter(field_name='prison__populations__name')

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

    card_expiry_date = django_filters.CharFilter(field_name='payment__card_expiry_date')
    card_number_last_digits = django_filters.CharFilter(field_name='payment__card_number_last_digits')
    sender_email = django_filters.CharFilter(field_name='payment__email', lookup_expr='icontains')
    sender_postcode = PostcodeFilter(field_name='payment__billing_address__postcode')

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

    class Meta:
        model = Credit
        fields = {
            'prisoner_number': ['exact'],
            'amount': ['exact', 'lte', 'gte'],
            'reviewed': ['exact'],
            'resolution': ['exact'],
            'log__action': ['exact']
        }


class CreditViewMixin(object):

    def get_queryset(self):
        queryset = Credit.objects.all()
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
    filter_backends = (DjangoFilterBackend, SafeOrderingFilter)
    filter_class = CreditListFilter
    ordering_fields = ('created', 'received_at', 'amount',
                       'prisoner_number', 'prisoner_name')
    action = 'list'

    permission_classes = (
        IsAuthenticated, CreditPermissions, get_client_permissions_class(
            CASHBOOK_OAUTH_CLIENT_ID, NOMS_OPS_OAUTH_CLIENT_ID,
            BANK_ADMIN_OAUTH_CLIENT_ID
        )
    )

    def get_queryset(self):
        return super().get_queryset().select_related('transaction').select_related('payment__batch')

    def get_serializer_class(self):
        if self.request.user.has_perm(
                'transaction.view_bank_details_transaction'):
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
    filter_class = CreditListFilter
    action = 'list'

    def get_queryset(self):
        return super().get_queryset().filter(
            Credit.STATUS_LOOKUP[CREDIT_STATUS.CREDITED],
            log__action=LOG_ACTIONS.CREDITED
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
        return self.queryset.filter(user=self.request.user).order_by('-id')
