from functools import cmp_to_key, reduce
import logging
import re

from django.contrib.auth import get_user_model
from django.db import connection, models, transaction
import django_filters
from django.http import HttpResponseRedirect
from django.views.generic import View
from rest_framework import generics, filters, status as drf_status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings

from core import dictfetchall
from core.filters import StatusChoiceFilter
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    CashbookClientIDPermissions, NomsOpsCashbookClientIDPermissions,
    NomsOpsClientIDPermissions
)
from prison.models import Prison
from transaction.pagination import DateBasedPagination
from .constants import CREDIT_STATUS, LOCK_LIMIT
from .models import Credit
from .permissions import CreditPermissions
from .serializers import (
    CreditSerializer, SecurityCreditSerializer, CreditedOnlyCreditSerializer,
    IdsCreditSerializer, LockedCreditSerializer, SenderSerializer,
    PrisonerSerializer
)
from .signals import credit_prisons_need_updating

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
                    amount = matches.group(1).replace('.', '')
                    return models.Q(**{'%s__startswith' % field: amount})
                elif field == 'sender_name':
                    return models.Q(**{'transaction__%s__icontains' % field: word})

                return models.Q(**{'%s__icontains' % field: word})

            qs = qs.filter(
                reduce(
                    lambda a, b: a | b,
                    filter(bool, map(get_field_filter, self.fields))
                )
            )
        return qs


class CreditListFilter(django_filters.FilterSet):

    status = StatusChoiceFilter(choices=CREDIT_STATUS.choices)
    prison = django_filters.ModelMultipleChoiceFilter(queryset=Prison.objects.all())
    prison_region = django_filters.CharFilter(name='prison__region')
    prison_gender = django_filters.CharFilter(name='prison__gender')
    user = django_filters.ModelChoiceFilter(name='owner', queryset=User.objects.all())
    received_at = django_filters.DateFromToRangeFilter()
    search = CreditTextSearchFilter()
    sender_name = django_filters.CharFilter(name='transaction__sender_name',
                                            lookup_expr='icontains')
    sender_sort_code = django_filters.CharFilter(name='transaction__sender_sort_code')
    sender_account_number = django_filters.CharFilter(name='transaction__sender_account_number')
    sender_roll_number = django_filters.CharFilter(name='transaction__sender_roll_number')

    class Meta:
        model = Credit
        fields = ('prisoner_number',)


class CreditViewMixin(object):

    def get_queryset(self):
        return Credit.objects.filter(
            prison__in=PrisonUserMapping.objects.get_prison_set_for_user(self.request.user)
        )


class GetCredits(CreditViewMixin, generics.ListAPIView):
    filter_backends = (filters.DjangoFilterBackend, filters.OrderingFilter)
    filter_class = CreditListFilter
    ordering_fields = ('created',)
    action = 'list'

    permission_classes = (
        IsAuthenticated, NomsOpsCashbookClientIDPermissions,
        CreditPermissions
    )

    def get_serializer_class(self):
        if self.request.user.has_perm(
                'transaction.view_bank_details_transaction'):
            return SecurityCreditSerializer
        else:
            return CreditSerializer


class DatePaginatedCredits(GetCredits):
    pagination_class = DateBasedPagination


class CreditCredits(CreditViewMixin, generics.GenericAPIView):
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

        credit_ids = [x['id'] for x in deserialized.data]
        with transaction.atomic():
            to_update = self.get_queryset().filter(
                owner=request.user,
                pk__in=credit_ids
            ).select_for_update()

            ids_to_update = [c.id for c in to_update]
            conflict_ids = set(credit_ids) - set(ids_to_update)

            if conflict_ids:
                conflict_ids = sorted(conflict_ids)
                logger.warning('Some credits were not credited: [%s]' %
                               ', '.join(map(str, conflict_ids)))
                return Response(
                    data={
                        'errors': [
                            {
                                'msg': 'Some credits could not be credited.',
                                'ids': conflict_ids,
                            }
                        ]
                    },
                    status=drf_status.HTTP_409_CONFLICT
                )

            for item in deserialized.data:
                obj = to_update.get(pk=item['id'])
                obj.credit_prisoner(credited=item['credited'], by_user=request.user)

        return Response(status=drf_status.HTTP_204_NO_CONTENT)


class CreditList(View):
    """
    Dispatcher View that dispatches to GetCredits or CreditCredits
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
        return view.as_view()(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return CreditCredits.as_view()(request, *args, **kwargs)


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
            **Credit.STATUS_LOOKUP[CREDIT_STATUS.LOCKED]
        )


class LockCredits(CreditViewMixin, APIView):
    action = 'lock'

    permission_classes = (
        IsAuthenticated, CashbookClientIDPermissions,
        CreditPermissions
    )

    def post(self, request, format=None):
        with transaction.atomic():
            locked_count = self.get_queryset().locked().filter(owner=self.request.user).count()
            if locked_count < LOCK_LIMIT:
                slice_size = LOCK_LIMIT-locked_count
                to_lock = self.get_queryset().available().select_for_update()
                slice_pks = to_lock.values_list('pk', flat=True)[:slice_size]

                queryset = self.get_queryset().filter(pk__in=slice_pks)
                for c in queryset:
                    c.lock(by_user=request.user)

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
        with transaction.atomic():
            to_update = self.get_queryset().locked().filter(pk__in=credit_ids).select_for_update()

            ids_to_update = [c.id for c in to_update]
            conflict_ids = set(credit_ids) - set(ids_to_update)

            if conflict_ids:
                conflict_ids = sorted(conflict_ids)
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
            for c in to_update:
                c.unlock(by_user=request.user)

        credit_prisons_need_updating.send(sender=Credit)

        redirect_url = '{url}?user={user}&status={status}'.format(
            url=reverse('credit-list'),
            user=request.user.pk,
            status=CREDIT_STATUS.AVAILABLE
        )
        return HttpResponseRedirect(redirect_url, status=drf_status.HTTP_303_SEE_OTHER)


class GroupedListAPIView(generics.ListAPIView):
    ordering_param = api_settings.ORDERING_PARAM
    ordering_fields = ()
    default_ordering = ()

    def get_ordering(self):
        params = self.request.query_params.get(self.ordering_param, '')
        params = [param for param in map(str.strip, params.split(','))
                  if param in self.ordering_fields or param.lstrip('-') in self.ordering_fields]
        return params or self.default_ordering

    def paginate_queryset(self, queryset):
        queryset = self.get_ordered_queryset(queryset)
        page = super().paginate_queryset(queryset)
        return page

    def get_ordered_queryset(self, queryset):
        # NB: queryset is a *list* of dicts
        ordering = self.get_ordering()
        if not ordering:
            return queryset

        if len(ordering) == 1:
            field = ordering[0]
            reverse_order = False
            if field[0] == '-':
                field = field[1:]
                reverse_order = True
            return sorted(queryset, key=lambda item: item[field], reverse=reverse_order)

        def compare(a, b):
            for field in ordering:
                reverse_order = False
                if field[0] == '-':
                    field = field[1:]
                    reverse_order = True
                a_value = a[field]
                b_value = b[field]
                if a_value == b_value:
                    continue
                if a_value < b_value:
                    key = -1
                else:
                    key = 1
                if reverse_order:
                    key = -key
                return key
            return 0

        return sorted(queryset, key=cmp_to_key(compare))


class SenderList(CreditViewMixin, GroupedListAPIView):
    serializer_class = SenderSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = CreditListFilter
    ordering_fields = ('prisoner_count', 'credit_count', 'credit_total', 'sender_name')
    default_ordering = ('-prisoner_count',)
    action = 'list'

    permission_classes = (
        IsAuthenticated, NomsOpsClientIDPermissions,
        CreditPermissions
    )

    def get_queryset(self):
        # restrict by prison access, but include refunds
        return super().get_queryset() | Credit.objects.filter(prison=None)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        filtered_ids = tuple(queryset.values_list('pk'))
        if not filtered_ids:
            return []

        min_prisoner_count = self.request.query_params.get('min_prisoner_count', 0)
        max_prisoner_count = self.request.query_params.get('max_prisoner_count', 99999)

        cursor = connection.cursor()
        cursor.execute('''
            SELECT
                t.sender_name AS sender_name,
                t.sender_sort_code AS sender_sort_code,
                t.sender_account_number AS sender_account_number,
                t.sender_roll_number AS sender_roll_number,
                c.prisoner_number AS prisoner_number,
                c.prisoner_name AS prisoner_name,
                c.prison_id AS prison_id,
                COUNT(*) AS credit_count,
                SUM(c.amount) AS credit_total
            FROM credit_credit c INNER JOIN transaction_transaction t ON t.credit_id=c.id
            WHERE c.id IN %s AND (
                SELECT COUNT(*)>=%s AND COUNT(*)<=%s FROM (
                    SELECT 1 FROM credit_credit c2
                    INNER JOIN transaction_transaction t2 ON t2.credit_id = c2.id
                    WHERE c2.id IN %s AND
                          c2.prisoner_number IS NOT NULL AND
                          t2.sender_name=t.sender_name AND
                          t2.sender_sort_code=t.sender_sort_code AND
                          t2.sender_account_number=t.sender_account_number AND
                          t2.sender_roll_number=t.sender_roll_number
                    GROUP BY c2.prisoner_number
                ) AS s
            )
            GROUP BY t.sender_name, t.sender_sort_code, t.sender_account_number,
            t.sender_roll_number, c.prisoner_number, c.prisoner_name, c.prison_id
            ORDER BY t.sender_sort_code, t.sender_account_number,
            t.sender_roll_number, t.sender_name;
        ''', [filtered_ids, min_prisoner_count, max_prisoner_count, filtered_ids])

        grouped_credits = dictfetchall(cursor)

        senders = []
        last_sender = None
        sender_identifiers = ('sender_name', 'sender_sort_code', 'sender_account_number', 'sender_roll_number')
        for credit_group in grouped_credits:
            prisoner = {
                'prisoner_number': credit_group['prisoner_number'],
                'prisoner_name': credit_group['prisoner_name'],
                'prison_id': credit_group['prison_id'],
                'credit_count': credit_group['credit_count'],
                'credit_total': credit_group['credit_total'],
            }
            if last_sender and all(last_sender[key] == credit_group[key]
                                   for key in sender_identifiers):
                last_sender['prisoners'].append(prisoner)
            else:
                last_sender = {
                    key: credit_group[key]
                    for key in sender_identifiers
                }
                last_sender.update({
                    'prisoners': [prisoner],
                    'prisoner_count': 0,
                    'credit_count': 0,
                    'credit_total': 0,
                })
                senders.append(last_sender)
            last_sender['credit_count'] += prisoner['credit_count']
            last_sender['credit_total'] += prisoner['credit_total']
            if prisoner['prisoner_number'] is not None:
                last_sender['prisoner_count'] += 1
        return senders


class PrisonerList(CreditViewMixin, GroupedListAPIView):
    serializer_class = PrisonerSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = CreditListFilter
    ordering_fields = ('sender_count', 'credit_count', 'credit_total', 'prisoner_name', 'prisoner_number')
    default_ordering = ('-sender_count',)
    action = 'list'

    permission_classes = (
        IsAuthenticated, NomsOpsClientIDPermissions,
        CreditPermissions
    )

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        filtered_ids = tuple(queryset.values_list('pk'))
        if not filtered_ids:
            return []

        min_sender_count = self.request.query_params.get('min_sender_count', 0)
        max_sender_count = self.request.query_params.get('max_sender_count', 99999)

        cursor = connection.cursor()
        cursor.execute('''
            SELECT
                t.sender_name AS sender_name,
                t.sender_sort_code AS sender_sort_code,
                t.sender_account_number AS sender_account_number,
                t.sender_roll_number AS sender_roll_number,
                c.prisoner_number AS prisoner_number,
                c.prisoner_name AS prisoner_name,
                c.prison_id AS prison_id,
                COUNT(*) AS credit_count,
                SUM(c.amount) AS credit_total
            FROM credit_credit c INNER JOIN transaction_transaction t ON t.credit_id=c.id
            WHERE c.id IN %s AND (
                SELECT COUNT(*)>=%s AND COUNT(*)<=%s FROM (
                    SELECT 1 FROM credit_credit c2
                    INNER JOIN transaction_transaction t2 ON t2.credit_id = c2.id
                    WHERE c2.id IN %s AND c2.prisoner_number=c.prisoner_number
                    GROUP BY t2.sender_name, t2.sender_sort_code,
                    t2.sender_account_number, t2.sender_roll_number
                ) AS s
            )
            GROUP BY t.sender_name, t.sender_sort_code, t.sender_account_number,
            t.sender_roll_number, c.prisoner_number, c.prisoner_name, c.prison_id
            ORDER BY c.prisoner_number;
        ''', [filtered_ids, min_sender_count, max_sender_count, filtered_ids])

        grouped_credits = dictfetchall(cursor)

        prisoners = []
        last_prisoner = None
        prisoner_identifiers = ('prisoner_number',)
        for credit_group in grouped_credits:
            sender = {
                'sender_name': credit_group['sender_name'],
                'sender_sort_code': credit_group['sender_sort_code'],
                'sender_account_number': credit_group['sender_account_number'],
                'sender_roll_number': credit_group['sender_roll_number'],
                'credit_count': credit_group['credit_count'],
                'credit_total': credit_group['credit_total'],
            }
            if last_prisoner and all(last_prisoner[key] == credit_group[key]
                                     for key in prisoner_identifiers):
                last_prisoner['senders'].append(sender)
            else:
                last_prisoner = {
                    key: credit_group[key]
                    for key in prisoner_identifiers
                }
                last_prisoner.update({
                    'prisoner_name': credit_group['prisoner_name'],
                    'prison_id': credit_group['prison_id'],
                    'senders': [sender],
                    'sender_count': 0,
                    'credit_count': 0,
                    'credit_total': 0,
                })
                prisoners.append(last_prisoner)
            last_prisoner['credit_count'] += sender['credit_count']
            last_prisoner['credit_total'] += sender['credit_total']
            last_prisoner['sender_count'] += 1
        return prisoners
