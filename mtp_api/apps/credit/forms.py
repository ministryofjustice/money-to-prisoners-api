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

        def get_sql_filter(self, expression=field_name):
            # NB: this performs no SQL escaping so should only be called from a valid form,
            # take care what goes into `expression`
            lower_value, upper_value = getattr(self, get_range_attribute)()
            if lower_value is None and upper_value is None:
                return SQLFragment(None, [])
            if lower_value == upper_value:
                return SQLFragment('%s = %%s' % expression, [lower_value])
            if lower_value is None:
                return SQLFragment('%s <= %%s' % expression, [upper_value])
            if upper_value is None:
                return SQLFragment('%s >= %%s' % expression, [lower_value])
            return SQLFragment('%s BETWEEN %%s and %%s' % expression, [lower_value, upper_value])

        setattr(cls, get_range_attribute, get_range)
        setattr(cls, 'clean_' + upper, clean)
        setattr(cls, 'get_%s_sql_filter' % field_name, get_sql_filter)
        return cls

    return inner


@range_field_decorations('credit_count')
@range_field_decorations('credit_total')
class GroupedListFilterForm(forms.Form):
    credit_count_0 = forms.IntegerField(required=False, min_value=1)
    credit_count_1 = forms.IntegerField(required=False, min_value=1)
    credit_total_0 = forms.IntegerField(required=False)
    credit_total_1 = forms.IntegerField(required=False)


@range_field_decorations('prisoner_count')
class SenderListFilterForm(GroupedListFilterForm):
    prisoner_count_0 = forms.IntegerField(required=False, min_value=1)
    prisoner_count_1 = forms.IntegerField(required=False, min_value=1)


@range_field_decorations('sender_count')
class PrisonerListFilterForm(GroupedListFilterForm):
    sender_count_0 = forms.IntegerField(required=False, min_value=1)
    sender_count_1 = forms.IntegerField(required=False, min_value=1)
