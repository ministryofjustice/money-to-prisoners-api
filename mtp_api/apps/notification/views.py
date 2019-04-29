from collections import OrderedDict

from django.db.models import Subquery, OuterRef, F
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets, views, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.filters import IsoDateTimeFilter, SafeOrderingFilter
from core.permissions import ActionsBasedPermissions
from prison.models import Prison
from .constants import EMAIL_FREQUENCY
from .models import Event, EmailNotificationPreferences
from .rules import RULES
from .serializers import EventSerializer


class GroupByProfileFilter(django_filters.CharFilter):
    def filter(self, qs, value):
        if value in ['sender_profile', 'recipient_profile', 'prisoner_profile']:
            group_field = '%s_event__%s' % (value, value)
            qs = qs.annotate(
                latest=Subquery(
                    qs.filter(
                        **{group_field: OuterRef(group_field)}
                    ).order_by('-triggered_at').values('id')[:1]
                )
            ).filter(id=F('latest'))
        return qs


class EventViewFilter(django_filters.FilterSet):
    triggered_at__lt = IsoDateTimeFilter(
        field_name='triggered_at', lookup_expr='lt'
    )
    triggered_at__gte = IsoDateTimeFilter(
        field_name='triggered_at', lookup_expr='gte'
    )
    for_credit = django_filters.BooleanFilter(
        field_name='credit_event', lookup_expr='isnull', exclude=True
    )
    for_disbursement = django_filters.BooleanFilter(
        field_name='disbursement_event', lookup_expr='isnull', exclude=True
    )
    for_sender_profile = django_filters.BooleanFilter(
        field_name='sender_profile_event', lookup_expr='isnull', exclude=True
    )
    for_recipient_profile = django_filters.BooleanFilter(
        field_name='recipient_profile_event', lookup_expr='isnull', exclude=True
    )
    for_prisoner_profile = django_filters.BooleanFilter(
        field_name='prisoner_profile_event', lookup_expr='isnull', exclude=True
    )
    group_by = GroupByProfileFilter()
    credit_prison = django_filters.ModelMultipleChoiceFilter(
        field_name='credit_event__credit__prison',
        queryset=Prison.objects.all()
    )
    disbursement_prison = django_filters.ModelMultipleChoiceFilter(
        field_name='disbursement_event__disbursement__prison',
        queryset=Prison.objects.all()
    )

    class Meta:
        model = Event
        fields = {
            'rule': ['exact'],
        }


class EventView(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Event.objects.all().order_by('id').prefetch_related(
        'credit_event__credit'
    ).prefetch_related(
        'disbursement_event__disbursement'
    ).prefetch_related(
        'sender_profile_event__sender_profile'
    ).prefetch_related(
        'recipient_profile_event__recipient_profile'
    ).prefetch_related(
        'prisoner_profile_event__prisoner_profile'
    )
    serializer_class = EventSerializer
    filter_backends = (DjangoFilterBackend, SafeOrderingFilter,)
    filter_class = EventViewFilter

    permission_classes = (IsAuthenticated, ActionsBasedPermissions)


class RuleView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        rules = []
        for rule in RULES:
            rule_dict = {
                'code': rule,
                'description': RULES[rule].description
            }
            rules.append(rule_dict)

        return Response(OrderedDict([
            ('count', len(rules)),
            ('next', None),
            ('previous', None),
            ('results', rules)
        ]))


class EmailPreferencesView(viewsets.ViewSet):
    permission_classes = (IsAuthenticated,)

    def list(self, request, *args, **kwargs):
        try:
            frequency = EmailNotificationPreferences.objects.get(
                user=request.user
            ).frequency
        except EmailNotificationPreferences.DoesNotExist:
            frequency = EMAIL_FREQUENCY.NEVER
        return Response(
            {'frequency': frequency}
        )

    def create(self, request, *args, **kwargs):
        frequency = request.data.get('frequency')
        if frequency not in EMAIL_FREQUENCY.values:
            return Response(
                'Must provide a recognized "frequency" value',
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        EmailNotificationPreferences.objects.filter(user=user).delete()
        if frequency != EMAIL_FREQUENCY.NEVER:
            EmailNotificationPreferences.objects.create(
                user=user, frequency=frequency
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
