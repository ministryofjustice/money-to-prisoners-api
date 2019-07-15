from django.db.models import Q
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, views, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.filters import IsoDateTimeFilter, SafeOrderingFilter, MultipleValueFilter
from core.models import TruncLocalDate
from core.permissions import ActionsBasedPermissions
from mtp_auth.permissions import NomsOpsClientIDPermissions
from notification.constants import EMAIL_FREQUENCY
from notification.models import Event, EmailNotificationPreferences
from notification.rules import RULES, ENABLED_RULES
from notification.serializers import EventSerializer


class EventPagesView(views.APIView):
    permission_classes = (IsAuthenticated, NomsOpsClientIDPermissions)

    def get(self, request):
        filters = Q(user=self.request.user) | Q(user__isnull=True)
        rules = request.query_params.getlist('rule')
        if rules:
            filters &= Q(rule__in=rules)
        offset = int(request.query_params.get('offset', 0))
        limit = int(request.query_params.get('limit', 25))

        queryset = Event.objects \
            .annotate(triggered_at_date=TruncLocalDate('triggered_at')) \
            .filter(filters) \
            .values('triggered_at_date') \
            .order_by('-triggered_at_date') \
            .distinct()
        count = queryset.count()
        results = list(queryset[offset:offset + limit])
        return Response({
            'newest': results[0]['triggered_at_date'] if results else None,
            'oldest': results[-1]['triggered_at_date'] if results else None,
            'count': count,
        })


class EventViewFilter(django_filters.FilterSet):
    triggered_at__lt = IsoDateTimeFilter(
        field_name='triggered_at', lookup_expr='lt'
    )
    triggered_at__gte = IsoDateTimeFilter(
        field_name='triggered_at', lookup_expr='gte'
    )
    rule = MultipleValueFilter()

    class Meta:
        model = Event
        fields = {}


class EventView(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Event.objects.all().order_by('-triggered_at', 'id').prefetch_related(
        'prisoner_profile_event__prisoner_profile',
        'sender_profile_event__sender_profile',
        'recipient_profile_event__recipient_profile',
    )
    serializer_class = EventSerializer
    filter_backends = (DjangoFilterBackend, SafeOrderingFilter,)
    filter_class = EventViewFilter

    permission_classes = (IsAuthenticated, ActionsBasedPermissions, NomsOpsClientIDPermissions)

    def get_queryset(self):
        return self.queryset.filter(
            Q(user=self.request.user) | Q(user__isnull=True)
        )


class RuleView(views.APIView):
    permission_classes = (IsAuthenticated, NomsOpsClientIDPermissions)

    def get(self, _request):
        rules = [
            {'code': rule, 'description': RULES[rule].description}
            for rule in RULES
            if rule in ENABLED_RULES
        ]
        return Response({
            'count': len(rules),
            'next': None,
            'previous': None,
            'results': rules,
        })


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
