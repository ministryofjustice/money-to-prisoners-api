from django import template
from django.utils.translation import gettext

from transaction.utils import format_amount, format_number, format_percentage

register = template.Library()


@register.filter(name='format_amount')
def format_amount_filter(value):
    return format_amount(value, trim_empty_pence=True) or '—'


@register.filter(name='format_number')
def format_number_filter(value):
    if value is None:
        return '—'
    if isinstance(value, (int, float)):
        return format_number(value)
    return value


@register.filter(name='format_percentage')
def format_percentage_filter(value):
    if value is None:
        return '–'
    return format_percentage(value)


@register.filter
def format_timedelta(value):
    if value is None:
        return '–'
    return gettext('%0.1f days') % (value.days + value.seconds / 86400)
