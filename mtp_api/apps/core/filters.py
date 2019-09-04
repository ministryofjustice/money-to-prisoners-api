import re
from functools import reduce
from operator import or_

from django import forms
from django.db.models import Q
from django.utils import six
from django.utils.dateparse import parse_datetime
from django.utils.formats import get_format
from django.utils.functional import lazy
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
import django_filters
import django_filters.fields
import django_filters.utils

from mtp_auth.permissions import NomsOpsClientIDPermissions

from user_event_log.utils import record_user_event
from user_event_log.constants import USER_EVENT_KINDS


class MultipleFieldCharFilter(django_filters.CharFilter):
    def __init__(self, *args, **kwargs):
        distinct = kwargs.get('distinct', True)
        kwargs['distinct'] = distinct

        conjoined = kwargs.pop('conjoined', False)
        self.conjoined = conjoined

        super().__init__(*args, **kwargs)

    def filter(self, qs, value):
        if isinstance(value, django_filters.fields.Lookup):
            lookup = six.text_type(value.lookup_type)
            value = value.value
        else:
            lookup = self.lookup_expr
        if value in ([], (), {}, None, ''):
            return qs

        q = Q()
        for n in set(self.field_name):
            if self.conjoined:
                qs = self.get_method(qs)(**{'%s__%s' % (n, lookup): value})
            else:
                q |= Q(**{'%s__%s' % (n, lookup): value})

        if self.distinct:
            return self.get_method(qs)(q).distinct()
        return self.get_method(qs)(q)

    @property
    def label(self):
        if self._label is None and hasattr(self, 'parent'):
            model = self.parent._meta.model
            fields = []
            for name in self.field_name:
                fields.append(django_filters.utils.label_for_filter(
                    model, name, self.lookup_expr, self.exclude
                ))
            self._label = ', '.join(fields)
        return self._label

    @label.setter
    def label(self, value):
        self._label = value


class SplitTextInMultipleFieldsFilter(django_filters.CharFilter):
    """
    Filters using a text search.
    Works by splitting the input into words and matches any object
    that have *all* of these words in *any* of the fields in "field_names".
    """
    def __init__(self, *args, field_names=(), **kwargs):
        super().__init__(*args, **kwargs)

        if not field_names:
            raise ValueError('The field_names keyword argument must be specified')

        self.field_names = field_names

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs

        if self.distinct:
            qs = qs.distinct()

        filters = []
        for word in value.split():
            word_qs = [
                Q(**{
                    f'{field}__{self.lookup_expr}': word,
                })
                for field in self.field_names
            ]
            filters.append(reduce(or_, word_qs))
        return self.get_method(qs)(*filters)


class BlankStringFilter(django_filters.BooleanFilter):
    def filter(self, qs, value):
        if value:
            qs = self.get_method(qs)(**{'%s__exact' % self.field_name: ''})
        return qs


class StatusChoiceFilter(django_filters.ChoiceFilter):
    def filter(self, qs, value):
        if value:
            qs = qs.filter(qs.model.STATUS_LOOKUP[value.lower()])
        return qs


def get_all_format(format_type, lang=None, use_l10n=None):
    return ['iso8601'] + get_format(format_type, lang, use_l10n)


get_all_format_lazy = lazy(get_all_format, six.text_type, list, tuple)


class IsoDateTimeField(forms.DateTimeField):
    input_formats = get_all_format_lazy('DATETIME_INPUT_FORMATS')

    def strptime(self, value, format):
        if format == 'iso8601':
            datetime = parse_datetime(value)
            if datetime is None:
                raise ValueError
            return datetime
        return super().strptime(value, format)


class IsoDateTimeFilter(django_filters.DateTimeFilter):
    field_class = IsoDateTimeField


class SafeOrderingFilter(OrderingFilter):
    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if ordering and 'id' not in ordering:
            return list(ordering) + ['id']
        return ordering


class MultipleValueField(forms.MultipleChoiceField):
    def valid_value(self, value):
        return True


class MultipleValueFilter(django_filters.MultipleChoiceFilter):
    field_class = MultipleValueField


def annotate_filter(filter_, annotations):
    base_filter = filter_.filter

    def annotated_filter(qs, value):
        return base_filter(qs.annotate(**annotations), value)

    filter_.filter = annotated_filter
    return filter_


class PostcodeFilter(django_filters.CharFilter):
    """
    Filters by postcode. It supports whitespaces, lower/uppercases etc.
    """
    def __init__(self, **kwargs):
        if 'lookup_expr' in kwargs:
            raise ValueError('You cannot override the default lookup_expr.')

        kwargs['lookup_expr'] = 'iregex'
        super().__init__(**kwargs)

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs

        value = re.sub(r'[^0-9A-Za-z]+', '', value)
        value = r'\s*'.join(value)
        return super().filter(qs, value)


class LogNomsOpsSearchDjangoFilterBackend(DjangoFilterBackend):
    """
    DjangoFilterBackend which logs calls to `list` endpoint.

    The logged data is available in a UserEvent record with the filters used
    and the total number of results returned by the queryset.

    Note:
        - only calls via the NOMS OPS client are logged
        - only non-empty filter values are logged
        - OrderingFilter values are ignored as not part of the DjangoFilterBackend
        - only calls that pass the form validation are logged
        - the values logged are the ones cleaned via the underlying form
            to make sure the input data is not malicious
    """
    def _should_log(self, request, view, filterset):
        if not NomsOpsClientIDPermissions().has_permission(request, view):
            return False

        if view.action != 'list':
            return False

        return filterset.is_bound and filterset.form.is_valid()

    def _log(self, request, qs, filterset):
        filters_used = {
            name: value
            for name, value in filterset.form.cleaned_data.items()
            if value
        }
        # only log filters used and only log when pk is not a filter used
        #   (the credits GET object endpoint is currently implemented as list with a pk filter)
        if not filters_used or 'pk' in filters_used:
            return

        data = {
            'filters': filters_used,
            'results': qs.count(),
        }
        record_user_event(request, USER_EVENT_KINDS.NOMS_OPS_SEARCH, data)

    def filter_queryset(self, request, queryset, view):
        """
        Same as the parent `filter_queryset` but it also logs some calls.
        """
        filter_class = self.get_filter_class(view, queryset)

        if filter_class:
            filterset = filter_class(request.query_params, queryset=queryset, request=request)
            qs = filterset.qs

            if self._should_log(request, view, filterset):
                self._log(request, qs, filterset)

            return qs

        return queryset
