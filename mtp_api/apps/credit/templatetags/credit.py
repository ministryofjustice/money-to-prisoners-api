from django import template
from django.utils.translation import gettext

from transaction.utils import format_currency_truncated, format_number, format_percentage

register = template.Library()


@register.filter(name='currency_truncated')
def currency_truncated_filter(value, truncate_above):
    return format_currency_truncated(value, truncate_above=truncate_above) or '—'


@register.filter(name='format_number')
def format_number_filter(value, truncate_after=None):
    if value is None:
        return '—'
    if isinstance(value, (int, float)):
        return format_number(value, truncate_after)
    return value


@register.filter(name='format_percentage')
def format_percentage_filter(value):
    try:
        return format_percentage(float(value))
    except (TypeError, ValueError):
        return '—'


@register.filter
def format_timedelta(value):
    if value is None:
        return '–'
    return gettext('%0.1f days') % (value.days + value.seconds / 86400)
