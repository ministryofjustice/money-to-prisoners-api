from django import forms
from django.db.models import Q
from django.utils import six
from django.utils.dateparse import parse_datetime
from django.utils.formats import get_format
from django.utils.functional import lazy
import django_filters
from rest_framework.filters import OrderingFilter


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
        for n in set(self.name):
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
            for name in self.name:
                fields.append(django_filters.utils.label_for_filter(
                    model, name, self.lookup_expr, self.exclude
                ))
            self._label = ', '.join(fields)
        return self._label

    @label.setter
    def label(self, value):
        self._label = value


class BlankStringFilter(django_filters.BooleanFilter):
    def filter(self, qs, value):
        if value:
            qs = self.get_method(qs)(**{'%s__exact' % self.name: ''})
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
