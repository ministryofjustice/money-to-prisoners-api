from django import template

register = template.Library()


@register.simple_tag
def get_login_count(login_counts, prison, month):
    return login_counts[(prison, month)]
