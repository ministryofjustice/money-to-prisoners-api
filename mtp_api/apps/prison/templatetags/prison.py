from django import template

register = template.Library()


@register.filter
def short_prison_name(prison_name):
    if not isinstance(prison_name, str):
        return prison_name
    return prison_name.upper().lstrip('HMP').strip().title()
