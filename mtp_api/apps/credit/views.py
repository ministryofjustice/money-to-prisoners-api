from functools import reduce
import logging
import re

from django.contrib.auth import get_user_model
from django.db import models, transaction
import django_filters
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.views.generic import View
from rest_framework import generics, filters, mixins, status as drf_status, viewsets
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse

from core.filters import (
    BlankStringFilter, StatusChoiceFilter, IsoDateTimeFilter,
    MultipleFieldCharFilter, SafeOrderingFilter, MultipleValueFilter
)
from core.permissions import ActionsBasedPermissions
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    CashbookClientIDPermissions, NomsOpsClientIDPermissions,
    get_client_permissions_class, CASHBOOK_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID
)
from prison.models import Prison
from transaction.pagination import DateBasedPagination
from . import InvalidCreditStateException
from .constants import CREDIT_STATUS, CREDIT_SOURCE
from .models import Credit, Comment, ProcessingBatch
from .permissions import CreditPermissions
from .serializers import (
    CreditSerializer, SecurityCreditSerializer, CreditedOnlyCreditSerializer,
    IdsCreditSerializer, LockedCreditSerializer, CommentSerializer,
    ProcessingBatchSerializer
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
            Credit.STATUS_LOOKUP[CREDIT_STATUS.AVAILABLE] |
            Credit.STATUS_LOOKUP[CREDIT_STATUS.LOCKED] |
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


class CreditListFilter(django_filters.FilterSet):
    status = StatusChoiceFilter(choices=CREDIT_STATUS.choices)
    user = django_filters.ModelChoiceFilter(name='owner', queryset=User.objects.all())
    valid = ValidCreditFilter(widget=django_filters.widgets.BooleanWidget)

    prisoner_name = django_filters.CharFilter(name='prisoner_name', lookup_expr='icontains')
    prison = django_filters.ModelMultipleChoiceFilter(queryset=Prison.objects.all())
    prison__isnull = django_filters.BooleanFilter(name='prison', lookup_expr='isnull')
    prison_region = django_filters.CharFilter(name='prison__region')
    prison_category = MultipleValueFilter(name='prison__categories__name')
    prison_population = MultipleValueFilter(name='prison__populations__name')

    search = CreditTextSearchFilter()
    sender_name = MultipleFieldCharFilter(
        name=('transaction__sender_name', 'payment__cardholder_name',),
        lookup_expr='icontains'
    )
    sender_sort_code = django_filters.CharFilter(name='transaction__sender_sort_code')
    sender_account_number = django_filters.CharFilter(name='transaction__sender_account_number')
    sender_roll_number = django_filters.CharFilter(name='transaction__sender_roll_number')
    sender_name__isblank = BlankStringFilter(name='transaction__sender_name')
    sender_sort_code__isblank = BlankStringFilter(name='transaction__sender_sort_code')
    sender_account_number__isblank = BlankStringFilter(name='transaction__sender_account_number')
    sender_roll_number__isblank = BlankStringFilter(name='transaction__sender_roll_number')

    card_expiry_date = django_filters.CharFilter(
        name='payment__card_expiry_date')
    card_number_last_digits = django_filters.CharFilter(
        name='payment__card_number_last_digits')
    sender_email = django_filters.CharFilter(
        name='payment__email',
        lookup_expr='icontains'
    )

    exclude_amount__endswith = django_filters.CharFilter(
        name='amount', lookup_expr='endswith', exclude=True
    )
    exclude_amount__regex = django_filters.CharFilter(
        name='amount', lookup_expr='regex', exclude=True
    )
    amount__endswith = django_filters.CharFilter(
        name='amount', lookup_expr='endswith'
    )
    amount__regex = django_filters.CharFilter(
        name='amount', lookup_expr='regex'
    )

    received_at__lt = IsoDateTimeFilter(
        name='received_at', lookup_expr='lt'
    )
    received_at__gte = IsoDateTimeFilter(
        name='received_at', lookup_expr='gte'
    )
    source = CreditSourceFilter()
    pk = MultipleValueFilter(name='pk')

    class Meta:
        model = Credit
        fields = {
            'prisoner_number': ['exact'],
            'amount': ['exact', 'lte', 'gte'],
            'reviewed': ['exact'],
            'resolution': ['exact'],
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
    filter_backends = (filters.DjangoFilterBackend, SafeOrderingFilter)
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


class DatePaginatedCredits(GetCredits):
    pagination_class = DateBasedPagination


class MarkCreditedCredits(CreditViewMixin, generics.GenericAPIView):
    serializer_class = CreditedOnlyCreditSerializer
    action = 'patch_credited'

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

    def patch(self, request, format=None):
        deserialized = self.get_serializer(data=request.data, many=True)
        deserialized.is_valid(raise_exception=True)

        credit_ids = [x['id'] for x in deserialized.data if x['credited']]
        try:
            with transaction.atomic():
                Credit.objects.mark_credited(
                    self.get_queryset().filter(owner=request.user),
                    credit_ids,
                    request.user
                )
        except InvalidCreditStateException as e:
            conflict_ids = e.conflict_ids
            logger.warning('Some credits were not marked credited: [%s]' %
                           ', '.join(map(str, conflict_ids)))
            return Response(
                data={
                    'errors': [
                        {
                            'msg': 'Some credits could not be marked credited.',
                            'ids': conflict_ids,
                        }
                    ]
                },
                status=drf_status.HTTP_409_CONFLICT
            )

        return Response(status=drf_status.HTTP_204_NO_CONTENT)


class CreditList(View):
    """
    Dispatcher View that dispatches to GetCredits or MarkCreditedCredits
    depending on the method.

    The standard logic would not work in this case as:
    - the two endpoints need to do something quite different so better if
        they belong to different classes
    - we need specific permissions for the two endpoints so it's cleaner to
        use the same CreditPermissions for all the views
    """

    def get(self, request, *args, **kwargs):
        if DateBasedPagination.page_query_param in request.GET:
            view = DatePaginatedCredits
        else:
            view = GetCredits
        return view.as_view({'get': 'list'}, suffix='List')(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return MarkCreditedCredits.as_view()(request, *args, **kwargs)


class LockedCreditList(CreditViewMixin, generics.ListAPIView):
    serializer_class = LockedCreditSerializer
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ('created',)
    action = 'list'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        CreditPermissions
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(
            Credit.STATUS_LOOKUP[CREDIT_STATUS.LOCKED]
        )


class LockCredits(CreditViewMixin, APIView):
    action = 'lock'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        CreditPermissions
    )

    def post(self, request, format=None):
        try:
            Credit.objects.lock(self.get_queryset(), request.user)
        except InvalidCreditStateException as e:
            conflict_ids = e.conflict_ids
            logger.warning('Some credits could not be locked: [%s]' %
                           ', '.join(map(str, conflict_ids)))
            return Response(
                data={
                    'errors': [
                        {
                            'msg': 'Some credits could not be locked.',
                            'ids': conflict_ids,
                        }
                    ]
                },
                status=drf_status.HTTP_409_CONFLICT
            )

        redirect_url = '{url}?user={user}&status={status}'.format(
            url=reverse('credit-list'),
            user=request.user.pk,
            status=CREDIT_STATUS.LOCKED
        )
        return HttpResponseRedirect(redirect_url, status=drf_status.HTTP_303_SEE_OTHER)


class UnlockCredits(CreditViewMixin, APIView):
    serializer_class = IdsCreditSerializer
    action = 'unlock'

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
        try:
            Credit.objects.unlock(self.get_queryset(), credit_ids, request.user)
        except InvalidCreditStateException as e:
            conflict_ids = e.conflict_ids
            logger.warning('Some credits were not unlocked: [%s]' %
                           ', '.join(map(str, conflict_ids)))
            return Response(
                data={
                    'errors': [
                        {
                            'msg': 'Some credits could not be unlocked.',
                            'ids': conflict_ids,
                        }
                    ]
                },
                status=drf_status.HTTP_409_CONFLICT
            )

        redirect_url = '{url}?user={user}&status={status}'.format(
            url=reverse('credit-list'),
            user=request.user.pk,
            status=CREDIT_STATUS.AVAILABLE
        )
        return HttpResponseRedirect(redirect_url, status=drf_status.HTTP_303_SEE_OTHER)


class CreditCredits(CreditViewMixin, APIView):
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
            Credit.objects.credit(
                self.get_queryset(),
                credit_ids,
                request.user
            )

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
            Credit.objects.set_manual(
                self.get_queryset(),
                credit_ids,
                request.user
            )

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
        return self.queryset.filter(user=self.request.user)
