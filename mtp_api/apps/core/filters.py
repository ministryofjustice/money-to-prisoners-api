from django import forms

from django.utils import six
from django.utils.dateparse import parse_datetime
from django.utils.formats import get_format
from django.utils.functional import lazy
import django_filters


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
