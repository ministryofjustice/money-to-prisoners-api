from urllib.parse import quote

from django import template

register = template.Library()


@register.inclusion_tag('core/admin-choice-list.html')
def admin_choice_list(form, bound_field):
    query_prefix = '&'.join(
        '='.join(map(lambda param: quote(str(param)), (name, value)))
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


@register.inclusion_tag('admin/sortable-table-header.html')
def sortable_table_header(form, ordering, title):
    query_string_without_ordering = form.query_string_without_ordering
    current_ordering, reversed_order = form.get_ordering()
    ordering_query_string = ordering
    if ordering == current_ordering:
        if reversed_order:
            currently_sorted = 'descending'
        else:
            currently_sorted = 'ascending'
            ordering_query_string = f'-{ordering_query_string}'
    else:
        currently_sorted = None
    return {
        'title': title,
        'query_string_without_ordering': query_string_without_ordering,
        'ordering_query_string': ordering_query_string,
        'currently_sorted': currently_sorted,
    }
