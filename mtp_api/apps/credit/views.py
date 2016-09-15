import contextlib
from functools import cmp_to_key, reduce
import logging
import re

from django.contrib.auth import get_user_model
from django.db import connection, models, transaction
from django.forms import MultipleChoiceField
import django_filters
from django.http import HttpResponseRedirect
from django.utils.crypto import get_random_string
from django.views.generic import View
from rest_framework import generics, filters, status as drf_status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings

from core import dictfetchall
from core.filters import BlankStringFilter, StatusChoiceFilter
from mtp_auth.models import PrisonUserMapping
from mtp_auth.permissions import (
    CashbookClientIDPermissions, NomsOpsClientIDPermissions,
    get_client_permissions_class, CASHBOOK_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID, BANK_ADMIN_OAUTH_CLIENT_ID
)
from prison.models import Prison
from transaction.models import Transaction
from transaction.pagination import DateBasedPagination
from .constants import CREDIT_STATUS, LOCK_LIMIT
from .forms import SenderListFilterForm, PrisonerListFilterForm, SQLFragment
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
                    search_term = matches.group(1)
                    amount = search_term.replace('.', '')
                    # exact match if amount fully specified e.g. £5.00,
                    # startswith if not e.g. £5
                    if '.' in search_term:
                        return models.Q(**{'%s' % field: amount})
                    else:
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


class MultipleValueField(MultipleChoiceField):

    def valid_value(self, value):
        return True


class MultipleValueFilter(django_filters.MultipleChoiceFilter):
    field_class = MultipleValueField


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
    sender_name = django_filters.CharFilter(name='transaction__sender_name',
                                            lookup_expr='icontains')
    sender_sort_code = django_filters.CharFilter(name='transaction__sender_sort_code')
    sender_account_number = django_filters.CharFilter(name='transaction__sender_account_number')
    sender_roll_number = django_filters.CharFilter(name='transaction__sender_roll_number')
    sender_name__isblank = BlankStringFilter(name='transaction__sender_name')
    sender_sort_code__isblank = BlankStringFilter(name='transaction__sender_sort_code')
    sender_account_number__isblank = BlankStringFilter(name='transaction__sender_account_number')
    sender_roll_number__isblank = BlankStringFilter(name='transaction__sender_roll_number')

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

    class Meta:
        model = Credit
        fields = {
            'prisoner_number': ['exact'],
            'amount': ['exact', 'lte', 'gte'],
            'received_at': ['lt', 'gte'],
        }


class CreditViewMixin(object):

    def get_queryset(self):
        if self.request.user.has_perm('credit.view_any_credit'):
            return Credit.objects.all()
        else:
            queryset = Credit.objects.filter(
                prison__in=PrisonUserMapping.objects.get_prison_set_for_user(self.request.user)
            )
            return queryset


class GetCredits(CreditViewMixin, generics.ListAPIView):
    filter_backends = (filters.DjangoFilterBackend, filters.OrderingFilter)
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
        return super().get_queryset().select_related('transaction').select_related('payment')

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
            Credit.STATUS_LOOKUP[CREDIT_STATUS.LOCKED]
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
                to_lock = self.get_queryset().available()[:slice_size]

                for c in to_lock:
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


class GroupedListAPIView(CreditViewMixin, generics.ListAPIView):
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = CreditListFilter
    ordering_param = api_settings.ORDERING_PARAM
    ordering_fields = ()
    default_ordering = ()
    action = 'list'

    sender_identifiers = ('sender_name', 'sender_sort_code', 'sender_account_number', 'sender_roll_number')
    prisoner_identifiers = ('prisoner_number',)

    permission_classes = (
        IsAuthenticated, NomsOpsClientIDPermissions,
        CreditPermissions
    )

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

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        with self.create_caches(queryset) as (credit_table, grouped_credit_table):
            return self.get_grouped_data(credit_table, grouped_credit_table)

    @contextlib.contextmanager
    def create_caches(self, queryset):
        with connection.cursor() as cursor:
            credit_table = self.cache_filtered_credits(cursor, queryset)
            grouped_credit_table = self.cache_grouped_credits(cursor, credit_table)
            yield credit_table, grouped_credit_table
            cursor.execute('DROP TABLE "{table}"'.format(table=credit_table))
            cursor.execute('DROP TABLE "{table}"'.format(table=grouped_credit_table))

    @classmethod
    def cache_filtered_credits(cls, cursor, queryset):
        table = 'credit_credit_filtered_' + get_random_string(
            allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789'
        )
        queryset = queryset.values('id')
        queryset.query.clear_ordering(True)
        filtered_credits_sql, params = queryset.query.sql_with_params()
        cursor.execute('CREATE TEMPORARY TABLE "{}" (id INTEGER PRIMARY KEY)'.format(table))
        cursor.execute('INSERT INTO "{}" {}'.format(table, filtered_credits_sql), params)
        return table

    def cache_grouped_credits(self, cursor, credit_table):
        raise NotImplementedError

    def get_grouped_data(self, credit_table, grouped_credit_table):
        raise NotImplementedError

    def get_group_filters(self, grouped_credit_table):
        raise NotImplementedError


class SenderList(GroupedListAPIView):
    serializer_class = SenderSerializer
    ordering_fields = ('prisoner_count', 'credit_count', 'credit_total', 'sender_name')
    default_ordering = ('-prisoner_count',)

    def cache_grouped_credits(self, cursor, credit_table):
        table = 'credit_credit_sender_' + get_random_string(
            allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789'
        )
        field_types = {
            field: Transaction._meta.get_field(field).db_type(connection)
            for field in self.sender_identifiers
        }
        cursor.execute(
            '''
            CREATE TEMPORARY TABLE "{table}" (
                sender_name {sender_name},
                sender_sort_code {sender_sort_code},
                sender_account_number {sender_account_number},
                sender_roll_number {sender_roll_number},
                prisoner_count integer,
                credit_count integer,
                credit_total bigint
            )
            '''.format(
                table=table,
                **field_types
            )
        )
        cursor.execute(
            '''
            CREATE UNIQUE INDEX group_index
            ON "{table}"
            ({fields})
            '''.format(
                table=table,
                fields=', '.join(self.sender_identifiers),
            )
        )
        cursor.execute(
            '''
            INSERT INTO "{table}"
            SELECT t.sender_name, t.sender_sort_code, t.sender_account_number, t.sender_roll_number,
                COUNT(DISTINCT c.prisoner_number), COUNT(*), SUM(c.amount)
            FROM credit_credit c
            INNER JOIN "{credit_table}" ct ON ct.id=c.id
            INNER JOIN transaction_transaction t ON t.credit_id = c.id
            WHERE c.prison_id IS NOT NULL
            GROUP BY t.sender_name, t.sender_sort_code, t.sender_account_number, t.sender_roll_number
            '''.format(
                table=table,
                credit_table=credit_table,
            )
        )
        return table

    def get_grouped_data(self, credit_table, grouped_credit_table):
        sql = '''
            SELECT
                t.sender_name AS sender_name,
                t.sender_sort_code AS sender_sort_code,
                t.sender_account_number AS sender_account_number,
                t.sender_roll_number AS sender_roll_number,
                c.prisoner_number AS prisoner_number,
                c.prisoner_name AS prisoner_name,
                c.prison_id AS prison_id,
                p.name AS prison_name,
                cp.name AS current_prison_name,
                COUNT(*) AS credit_count,
                SUM(c.amount) AS credit_total
            FROM credit_credit c
            INNER JOIN "{credit_table}" ct ON ct.id=c.id
            INNER JOIN transaction_transaction t ON t.credit_id=c.id
            LEFT JOIN prison_prisonerlocation pl ON c.prisoner_number=pl.prisoner_number
            LEFT JOIN prison_prison p on c.prison_id=p.nomis_id
            LEFT JOIN prison_prison cp on pl.prison_id=cp.nomis_id
            {sql_where}
            GROUP BY t.sender_name, t.sender_sort_code, t.sender_account_number, t.sender_roll_number,
                c.prisoner_number, c.prisoner_name,
                c.prison_id, p.name, cp.name
            ORDER BY t.sender_sort_code, t.sender_account_number,
                t.sender_roll_number, t.sender_name
        '''
        sql_where, where_params = self.get_group_filters(grouped_credit_table)
        if sql_where:
            sql_where = 'WHERE ' + sql_where
        else:
            sql_where = ''
        sql = sql.format(
            credit_table=credit_table,
            sql_where=sql_where,
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, where_params)
            grouped_credits = dictfetchall(cursor)

        senders = []
        last_sender = None
        for credit_group in grouped_credits:
            prisoner = {
                'prisoner_number': credit_group['prisoner_number'],
                'prisoner_name': credit_group['prisoner_name'],
                'prison_id': credit_group['prison_id'],
                'prison_name': credit_group['prison_name'],
                'current_prison_name': credit_group['current_prison_name'],
                'credit_count': credit_group['credit_count'],
                'credit_total': credit_group['credit_total'],
            }
            # null out number if not matched
            if not prisoner['prison_id']:
                prisoner['prisoner_number'] = None
            if last_sender and all(last_sender[key] == credit_group[key]
                                   for key in self.sender_identifiers):
                add_new_prisoner = True
                if not prisoner['prison_id']:
                    for previous_prisoner in last_sender['prisoners']:
                        if not previous_prisoner['prison_id']:
                            previous_prisoner['credit_count'] += prisoner['credit_count']
                            previous_prisoner['credit_total'] += prisoner['credit_total']
                            add_new_prisoner = False
                if add_new_prisoner:
                    last_sender['prisoners'].append(prisoner)
            else:
                last_sender = {
                    key: credit_group[key]
                    for key in self.sender_identifiers
                }
                last_sender.update({
                    'prisoners': [prisoner],
                    'prisoner_count': 0,
                    'credit_count': 0,
                    'credit_total': 0,
                })
                senders.append(last_sender)
            if prisoner['prison_id'] is not None:
                # NB: counts and totals are only summed for valid credits (those that reach a prisoner)
                last_sender['credit_count'] += prisoner['credit_count']
                last_sender['credit_total'] += prisoner['credit_total']
                last_sender['prisoner_count'] += 1
        for sender in senders:
            sender['prisoners'] = sorted(
                sender['prisoners'],
                key=lambda p: (p['prisoner_number'] or '\uffff').lower()
            )
        return senders

    def get_group_filters(self, grouped_credit_table):
        form = SenderListFilterForm(data=self.request.query_params)
        if not form.is_valid():
            return SQLFragment('FALSE', [])

        sql_where, params = form.get_sql_filters()
        if sql_where:
            # NB: counts and totals are only summed for valid credits (those that reach a prisoner)
            return SQLFragment(
                '''
                (
                    SELECT {sql_where}
                    FROM {table} gc
                    WHERE gc.sender_name=t.sender_name AND
                          gc.sender_sort_code=t.sender_sort_code AND
                          gc.sender_account_number=t.sender_account_number AND
                          gc.sender_roll_number=t.sender_roll_number
                )
                '''.format(
                    sql_where=sql_where,
                    table=grouped_credit_table,
                ),
                params
            )
        return SQLFragment(None, [])


class PrisonerList(GroupedListAPIView):
    serializer_class = PrisonerSerializer
    ordering_fields = ('sender_count', 'credit_count', 'credit_total', 'prisoner_name', 'prisoner_number')
    default_ordering = ('-sender_count',)

    def filter_queryset(self, queryset):
        return super().filter_queryset(queryset.exclude(prison=None))

    def cache_grouped_credits(self, cursor, credit_table):
        table = 'credit_credit_prisoner_' + get_random_string(
            allowed_chars='abcdefghijklmnopqrstuvwxyz0123456789'
        )
        field_types = {
            field: Credit._meta.get_field(field).db_type(connection)
            for field in self.prisoner_identifiers
        }
        cursor.execute(
            '''
            CREATE TEMPORARY TABLE "{table}" (
                prisoner_number {prisoner_number},
                sender_count integer,
                credit_count integer,
                credit_total bigint
            )
            '''.format(
                table=table,
                **field_types
            )
        )
        cursor.execute(
            '''
            CREATE UNIQUE INDEX group_index
            ON "{table}"
            ({fields})
            '''.format(
                table=table,
                fields=', '.join(self.prisoner_identifiers),
            )
        )
        cursor.execute(
            '''
            INSERT INTO "{table}"
            WITH credit_transaction AS (
                SELECT c.prisoner_number, c.amount,
                    t.sender_name, t.sender_sort_code, t.sender_account_number, t.sender_roll_number
                FROM credit_credit c
                INNER JOIN "{credit_table}" ct ON ct.id=c.id
                INNER JOIN transaction_transaction t ON t.credit_id = c.id
                WHERE c.prison_id IS NOT NULL
            )
            SELECT ct.prisoner_number,
                (
                    SELECT COUNT(*) FROM (
                        SELECT DISTINCT ct2.sender_name, ct2.sender_sort_code,
                            ct2.sender_account_number, ct2.sender_roll_number
                        FROM credit_transaction ct2
                        WHERE ct.prisoner_number=ct2.prisoner_number
                    ) AS ct3
                ),
                COUNT(*), SUM(ct.amount)
            FROM credit_transaction ct
            GROUP BY ct.prisoner_number
            '''.format(
                table=table,
                credit_table=credit_table,
            )
        )
        return table

    def get_grouped_data(self, credit_table, grouped_credit_table):
        sql = '''
            SELECT
                t.sender_name AS sender_name,
                t.sender_sort_code AS sender_sort_code,
                t.sender_account_number AS sender_account_number,
                t.sender_roll_number AS sender_roll_number,
                c.prisoner_number AS prisoner_number,
                c.prisoner_name AS prisoner_name,
                c.prison_id AS prison_id,
                p.name AS prison_name,
                cp.name AS current_prison_name,
                COUNT(*) AS credit_count,
                SUM(c.amount) AS credit_total
            FROM credit_credit c
            INNER JOIN "{credit_table}" ct ON ct.id=c.id
            INNER JOIN transaction_transaction t ON t.credit_id=c.id
            LEFT JOIN prison_prisonerlocation pl ON c.prisoner_number=pl.prisoner_number
            LEFT JOIN prison_prison p on c.prison_id=p.nomis_id
            LEFT JOIN prison_prison cp on pl.prison_id=cp.nomis_id
            {sql_where}
            GROUP BY t.sender_name, t.sender_sort_code, t.sender_account_number, t.sender_roll_number,
                c.prisoner_number, c.prisoner_name,
                c.prison_id, p.name, cp.name
            ORDER BY c.prisoner_number
        '''
        sql_where, where_params = self.get_group_filters(grouped_credit_table)
        if sql_where:
            sql_where = 'WHERE ' + sql_where
        else:
            sql_where = ''
        sql = sql.format(
            credit_table=credit_table,
            sql_where=sql_where,
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, where_params)
            grouped_credits = dictfetchall(cursor)

        prisoners = []
        last_prisoner = None
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
                                     for key in self.prisoner_identifiers):
                last_prisoner['senders'].append(sender)
            else:
                last_prisoner = {
                    key: credit_group[key]
                    for key in self.prisoner_identifiers
                }
                last_prisoner.update({
                    'prisoner_name': credit_group['prisoner_name'],
                    'prison_id': credit_group['prison_id'],
                    'prison_name': credit_group['prison_name'],
                    'current_prison_name': credit_group['current_prison_name'],
                    'senders': [sender],
                    'sender_count': 0,
                    'credit_count': 0,
                    'credit_total': 0,
                })
                prisoners.append(last_prisoner)
            last_prisoner['credit_count'] += sender['credit_count']
            last_prisoner['credit_total'] += sender['credit_total']
            last_prisoner['sender_count'] += 1
        for prisoner in prisoners:
            prisoner['senders'] = sorted(
                prisoner['senders'],
                key=lambda s: (s['sender_name'] or '\uffff').lower()
            )
        return prisoners

    def get_group_filters(self, grouped_credit_table):
        form = PrisonerListFilterForm(data=self.request.query_params)
        if not form.is_valid():
            return SQLFragment('FALSE', [])

        sql_where, params = form.get_sql_filters()
        if sql_where:
            return SQLFragment(
                '''
                (
                    SELECT {sql_where}
                    FROM {table} gc
                    WHERE gc.prisoner_number=c.prisoner_number
                )
                '''.format(
                    sql_where=sql_where,
                    table=grouped_credit_table,
                ),
                params
            )
        return SQLFragment(None, [])
