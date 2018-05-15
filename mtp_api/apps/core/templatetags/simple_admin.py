from urllib.parse import quote

from django import template
from django.utils.encoding import force_text

register = template.Library()


@register.inclusion_tag('core/admin-choice-list.html')
def admin_choice_list(form, bound_field):
    query_prefix = '&'.join(
        '='.join(map(quote, map(force_text, (name, value))))
        for name, value in form.cleaned_data.items()
        if name != bound_field.name
    )
    if query_prefix:
        query_prefix += '&'
    return {
        'query_prefix': query_prefix,
        'field': bound_field,
        'choices': bound_field.field.choices,
    }
