import datetime
import logging
import math

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.lookups import DateTimeDateTransform
from django.db.models.sql.constants import QUERY_TERMS
from django.utils.timezone import make_aware
from rest_framework.exceptions import NotFound
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.utils.urls import replace_query_param

logger = logging.getLogger('mtp')


def parse_datetime(field, date_str):
    try:
        dt = field.to_python(date_str)
        if dt:
            return make_aware(dt)
    except ValidationError:
        pass
    return None


def normalise_datetime(date):
    dt = datetime.datetime(date.year, date.month, date.day)
    # NB: DateTimeDateTransform already converted dates into current time zone
    return make_aware(dt)


class DateBasedPagination(LimitOffsetPagination):
    def __init__(self):
        super().__init__()
        # defaults
        self.page = 1
        self.page_size = 5  # in number of days

        self.fallback = False
        self.count = 0
        self.page_count = 0

    def get_int_query_param(self, key, default, min_value, max_value=None):
        try:
            value = self.request.query_params[key]
            value = int(value)
            if value < min_value or max_value is not None and value > max_value:
                raise ValueError
            return value
        except (KeyError, ValueError):
            return default

    def paginate_queryset(self, queryset, request, view=None):
        page_by_date_field = request.query_params.get('page_by_date_field')
        if not page_by_date_field:
            # fall back to default limit-offset pagination
            self.fallback = True
            return super().paginate_queryset(queryset, request, view=view)

        ordering_field = request.query_params.get(api_settings.ORDERING_PARAM, page_by_date_field)
        if ordering_field not in (page_by_date_field, '-%s' % page_by_date_field):
            raise NotFound('Ordering must be done on the same field as pagination')

        # other filter already chooses an exact date so simply return results
        if request.query_params.get(page_by_date_field):
            return list(queryset)

        # restrict complex filters on same field as they're hard to combine
        for query_term in QUERY_TERMS:
            query_term = '%s__%s' % (page_by_date_field, query_term)
            if query_term in request.query_params:
                msg = 'Cannot combine pagination with complex filtering on the same field'
                logger.warning(msg)
                raise NotFound(msg)

        self.request = request

        # check if date-range filter exists
        field = queryset.model._meta.get_field(page_by_date_field)
        from_date_range = request.query_params.get('%s_0' % page_by_date_field)
        to_date_range = request.query_params.get('%s_1' % page_by_date_field)
        from_date_range = parse_datetime(field, from_date_range)
        to_date_range = parse_datetime(field, to_date_range)

        # convert field into date and select only this field
        dates = queryset.annotate(converted_date=DateTimeDateTransform(page_by_date_field)). \
            values_list('converted_date', flat=True)
        # count distinct dates for this field
        date_count = dates.aggregate(count=models.Count('converted_date', distinct=True))['count']

        # store values for pagination details
        try:
            self.count = queryset.count()
        except (AttributeError, TypeError):
            self.count = len(queryset)
        self.page = self.get_int_query_param('page', default=self.page, min_value=1)
        self.page_size = self.get_int_query_param('page_size', default=self.page_size, min_value=1, max_value=7)
        self.page_count = int(math.ceil(date_count / self.page_size))

        if self.page_count > 1:
            self.display_page_controls = True
        if self.page > 1 and self.page > self.page_count:
            raise NotFound('The page contains no results')

        # determine date-based filters
        reverse_order = ordering_field.startswith('-')
        order_by = '-converted_date' if reverse_order else 'converted_date'
        dates = dates.distinct('converted_date').order_by(order_by)
        dates = dates[(self.page - 1) * self.page_size:self.page * self.page_size]
        dates = list(dates)
        if reverse_order:
            from_date, to_date = dates[-1], dates[0]
        else:
            from_date, to_date = dates[0], dates[-1]
        from_date = normalise_datetime(from_date)
        to_date = normalise_datetime(to_date)
        if from_date_range is not None:
            from_date = max(from_date, from_date_range)
        if to_date_range is not None:
            to_date = min(to_date, to_date_range)

        filters = {
            '%s__range' % page_by_date_field: [from_date, to_date]
        }
        return list(queryset.filter(**filters))

    def _get_link(self, page):
        url = self.request.build_absolute_uri()
        return replace_query_param(url, 'page', page)

    def get_previous_link(self):
        if self.fallback:
            return super().get_previous_link()
        if self.page <= 1:
            return None
        return self._get_link(self.page - 1)

    def get_next_link(self):
        if self.fallback:
            return super().get_next_link()
        if self.page >= self.page_count:
            return None
        return self._get_link(self.page + 1)

    def get_paginated_response(self, data):
        if self.fallback:
            return super().get_paginated_response(data)
        return Response({
            'count': self.count,
            'page': self.page,
            'page_count': self.page_count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })
