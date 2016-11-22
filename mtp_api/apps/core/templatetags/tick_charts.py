import functools

from django import template
from django.core.exceptions import FieldError
from django.db import models
from django.utils.crypto import get_random_string

register = template.Library()


def mean(iterable):
    reduced = functools.reduce(lambda previous, value: (previous[0] + 1, previous[1] + value),
                               iterable, (0, 0))
    if reduced[0] == 0:
        return float('nan')
    return reduced[1] / reduced[0]


def get_aggregates(values, stride_field, value_field):
    try:
        return values.aggregate(min_stride=models.Min(stride_field), max_stride=models.Max(stride_field),
                                min_value=models.Min(value_field), max_value=models.Max(value_field),
                                count=models.Count('*'))
    except (AttributeError, FieldError):
        values = list(values)
        return {
            'min_stride': values[0][stride_field],
            'max_stride': values[-1][stride_field],
            'min_value': min(values, key=lambda value: value[value_field])[value_field],
            'max_value': max(values, key=lambda value: value[value_field])[value_field],
            'count': len(values),
        }


@register.inclusion_tag('core/tick-chart.html')
def tick_chart(queryset, stride_field, value_field, grouping_size=200, grouping_method='mean',
               width=610, height=50, inset=2, axes=True, highlight_negative=True):
    values = queryset.values(stride_field, value_field).order_by(stride_field)
    aggregates = get_aggregates(values, stride_field, value_field)
    if aggregates['count'] < 2:
        return {}

    if grouping_size and aggregates['count'] > grouping_size:
        # group large data sets by either averaging or summing the values
        # NB: if the queryset does not exactly divide into groups, the final items will be dropped
        if grouping_method == 'sum':
            grouping_method = sum
        elif grouping_method == 'mean':
            grouping_method = mean
        else:
            raise ValueError('Unknown group merge function')
        grouping_size = aggregates['count'] // grouping_size
        aggregates['count'] //= grouping_size
        values = [
            {
                stride_field: values[group * grouping_size][stride_field],
                value_field: grouping_method(
                    value[value_field]
                    for value in values[group * grouping_size:(group + 1) * grouping_size]
                ),
            }
            for group in range(aggregates['count'])
        ]
        aggregates = get_aggregates(values, stride_field, value_field)

    width = min(width, aggregates['count'] * 50)
    inner_width = width - inset * 2
    inner_height = height - inset * 2

    stride_span = aggregates['max_stride'] - aggregates['min_stride']
    min_value = min(type(aggregates['min_value'])(), aggregates['min_value'])
    value_span = aggregates['max_value'] - min_value

    negative_height = -min_value / value_span * inner_height
    positive_height = inner_height - negative_height

    values = (
        {
            'stride': (value[stride_field] - aggregates['min_stride']) / stride_span,  # range clamped to [0, 1]
            'value': (value[value_field] - min_value) / value_span,  # range between [-1, 1] and [0, 1]
        }
        for value in values
    )
    graph = (
        '%s%0.1f,%0.1f' % ('M' if index == 0 else 'L',
                           inset + value['stride'] * inner_width,
                           height - inset - value['value'] * inner_height)
        for index, value in enumerate(values)
    )

    context = {
        'width': width,
        'height': height,
        'inset': inset,
        'inner_height': inner_height,
        'inner_width': inner_width,
        'graph': ''.join(graph),
        'graph_id': get_random_string(4),
    }
    if axes:
        context['axes'] = {
            'zero_height': positive_height
        }
    if highlight_negative:
        clip_width = inner_width + inset
        positive_clip_height = positive_height + inset + 0.5
        negative_clip_height = negative_height + inset - 0.5
        context['clip'] = {
            'positive': (inset, 0, clip_width, positive_clip_height),
            'negative': (inset, positive_clip_height, clip_width, negative_clip_height),
        }
    return context
