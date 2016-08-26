from collections import namedtuple

from django import forms
from django.core.exceptions import ValidationError

SQLFragment = namedtuple('SQLFragment', ['query', 'params'])


def range_field_decorations(field_name):
    def inner(cls):
        lower = field_name + '_0'
        upper = field_name + '_1'
        get_range_attribute = 'get_%s_range' % field_name

        def get_range(self):
            return self.cleaned_data.get(lower), self.cleaned_data.get(upper)

        def clean(self):
            lower_value, upper_value = getattr(self, get_range_attribute)()
            if lower_value and upper_value and lower_value > upper_value:
                raise ValidationError('Must be larger than lower bound')
            return upper_value

        setattr(cls, get_range_attribute, get_range)
        setattr(cls, 'clean_' + upper, clean)
        return cls

    return inner


@range_field_decorations('credit_count')
@range_field_decorations('credit_total')
class GroupedListFilterForm(forms.Form):
    credit_count_0 = forms.IntegerField(required=False, min_value=1)
    credit_count_1 = forms.IntegerField(required=False, min_value=1)
    credit_total_0 = forms.IntegerField(required=False)
    credit_total_1 = forms.IntegerField(required=False)

    def get_sql_filters(self):
        sql_filters, params = [], []

        for field_name in self.range_fields:
            lower_value, upper_value = getattr(self, 'get_%s_range' % field_name)()
            if lower_value is None and upper_value is None:
                continue
            if lower_value == upper_value:
                sql_filters.append('%s = %%s' % field_name)
                params.append(lower_value)
            elif lower_value is None:
                sql_filters.append('%s <= %%s' % field_name)
                params.append(upper_value)
            elif upper_value is None:
                sql_filters.append('%s >= %%s' % field_name)
                params.append(lower_value)
            else:
                sql_filters.append('%s BETWEEN %%s and %%s' % field_name)
                params.extend([lower_value, upper_value])

        return SQLFragment(' AND '.join(filter(None, sql_filters)) or None,
                           params)


@range_field_decorations('prisoner_count')
class SenderListFilterForm(GroupedListFilterForm):
    prisoner_count_0 = forms.IntegerField(required=False, min_value=1)
    prisoner_count_1 = forms.IntegerField(required=False, min_value=1)

    range_fields = ('prisoner_count', 'credit_count', 'credit_total')


@range_field_decorations('sender_count')
class PrisonerListFilterForm(GroupedListFilterForm):
    sender_count_0 = forms.IntegerField(required=False, min_value=1)
    sender_count_1 = forms.IntegerField(required=False, min_value=1)

    range_fields = ('sender_count', 'credit_count', 'credit_total')
