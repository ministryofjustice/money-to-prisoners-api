import math

from django.conf import settings
from django.db import models
from django.db.models import DateTimeField
from django.template import Context, loader
from rest_framework.exceptions import NotFound
from rest_framework.pagination import BasePagination, _get_count as get_count
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.utils.urls import replace_query_param

from core.models import TruncUtcDate


class DateBasedPagination(BasePagination):
    page_query_param = 'page_by_date_field'
    template = 'rest_framework/pagination/previous_and_next.html'

    def __init__(self):
        super().__init__()
        # defaults
        self.page = 1
        self.page_size = settings.REQUEST_PAGE_DAYS  # in number of days

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
        page_by_date_field = request.query_params.get(self.page_query_param)
        if not page_by_date_field:
            raise NotFound('Pagination required `page_by_date_field` parameter')

        ordering_field = request.query_params.get(api_settings.ORDERING_PARAM, page_by_date_field)
        if ordering_field not in (page_by_date_field, '-%s' % page_by_date_field):
            raise NotFound('Ordering must be done on the same field as pagination')

        field = queryset.model._meta.get_field(page_by_date_field)
        if not isinstance(field, DateTimeField):
            raise NotFound('Pagination can only be done on a date field')

        # store pagination details
        self.request = request
        self.count = get_count(queryset)
        self.page = self.get_int_query_param('page', default=self.page, min_value=1)
        self.page_size = self.get_int_query_param('page_size', default=self.page_size, min_value=1, max_value=7)

        # convert field into date and select only this field
        dates = queryset.annotate(
            converted_date=TruncUtcDate(page_by_date_field)
        ).values_list('converted_date', flat=True)
        # count distinct dates for this field
        date_count = dates.aggregate(count=models.Count('converted_date', distinct=True))['count'] or 0

        self.page_count = int(math.ceil(date_count / self.page_size))
        if self.page_count > 1:
            self.display_page_controls = True
        if self.page > 1 and self.page > self.page_count:
            raise NotFound('Page %s contains no results' % self.page)

        # determine date-based filters
        reverse_order = ordering_field.startswith('-')
        order_by = '-converted_date' if reverse_order else 'converted_date'
        dates = dates.distinct('converted_date').order_by(order_by)
        dates = dates[(self.page - 1) * self.page_size:self.page * self.page_size]
        dates = list(dates)
        if len(dates) == 0:
            return list()
        if reverse_order:
            from_date, to_date = dates[-1], dates[0]
        else:
            from_date, to_date = dates[0], dates[-1]

        filters = {
            '%s__utcdate__range' % page_by_date_field: [from_date, to_date]
        }
        return list(queryset.filter(**filters))

    def _get_link(self, page):
        url = self.request.build_absolute_uri()
        return replace_query_param(url, 'page', page)

    def get_previous_link(self):
        if self.page <= 1:
            return None
        return self._get_link(self.page - 1)

    def get_next_link(self):
        if self.page >= self.page_count:
            return None
        return self._get_link(self.page + 1)

    def get_paginated_response(self, data):
        return Response({
            'count': self.count,
            'page': self.page,
            'page_count': self.page_count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })

    def get_html_context(self):
        return {
            'previous_url': self.get_previous_link(),
            'next_url': self.get_next_link()
        }

    def to_html(self):
        template = loader.get_template(self.template)
        context = Context(self.get_html_context())
        return template.render(context)
