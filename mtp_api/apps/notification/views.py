from collections import OrderedDict

from django.db.models import QuerySet
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from extended_choices import Choices
from rest_framework import filters, mixins, viewsets, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.filters import IsoDateTimeFilter
from core.permissions import ActionsBasedPermissions
from .models import Subscription, Event
from .rules import RULES
from .serializers import SubscriptionSerializer, EventSerializer


class SubscriptionView(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    queryset = Subscription.objects.all().order_by('id')
    serializer_class = SubscriptionSerializer

    permission_classes = (IsAuthenticated, ActionsBasedPermissions)

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class EventViewFilter(django_filters.FilterSet):
    created__lt = IsoDateTimeFilter(
        field_name='created', lookup_expr='lt'
    )
    created__gte = IsoDateTimeFilter(
        field_name='created', lookup_expr='gte'
    )

    class Meta:
        model = Event
        fields = ('created__lt', 'created__gte',)


class EventView(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Event.objects.all().order_by('id').prefetch_related(
        'credits').prefetch_related('disbursements')
    serializer_class = EventSerializer
    filter_backends = (DjangoFilterBackend, filters.OrderingFilter,)
    filter_class = EventViewFilter
    default_ordering = ('-pk',)

    permission_classes = (IsAuthenticated, ActionsBasedPermissions)

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)


class RuleView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        rules = []

        for rule in RULES:
            rule_dict = {
                'code': rule,
                'description': RULES[rule].description
            }
            inputs = []
            for input_field in RULES[rule].inputs:
                input_dict = {
                    'field': input_field.field,
                    'input_type': input_field.input_type,
                    'default_value': input_field.default_value,
                    'exclude': input_field.exclude
                }

                if input_field.choices and isinstance(input_field.choices, QuerySet):
                    input_dict['choices'] = [
                        (obj.pk, str(obj),) for obj in input_field.choices
                    ]
                elif input_field.choices and isinstance(input_field.choices, Choices):
                    input_dict['choices'] = input_field.choices.choices
                else:
                    input_dict['choices'] = input_field.choices
                inputs.append(input_dict)
            rule_dict['inputs'] = inputs
            rules.append(rule_dict)

        return Response(OrderedDict([
            ('count', len(rules)),
            ('next', None),
            ('previous', None),
            ('results', rules)
        ]))
