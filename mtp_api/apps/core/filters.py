from django import forms
from django.utils.dateparse import parse_datetime
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


class IsoDateTimeField(forms.DateTimeField):

    def strptime(self, value, format):
        datetime = parse_datetime(value)
        return datetime or super().strptime(value, format)


class IsoDateTimeFilter(django_filters.DateTimeFilter):
    field_class = IsoDateTimeField
