from django import template

from prison.models import Prison

register = template.Library()


@register.filter
def short_prison_name(prison_name):
    if not isinstance(prison_name, str):
        return prison_name
    return Prison.shorten_name(prison_name)
