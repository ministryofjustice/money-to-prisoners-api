from django.http import JsonResponse
from django.utils import timezone
from rest_framework import mixins, viewsets

from service.models import Downtime, SERVICES, Notification
from service.serializers import NotificationSerializer


def service_availability_view(_):
    def service_availability(service):
        downtime = Downtime.objects.active_downtime(service)
        if not downtime:
            return service, {'status': True}
        status = {
            'status': False,
        }
        if downtime.end:
            status['downtime_end'] = downtime.end.isoformat()
        if downtime.message_to_users:
            status['message_to_users'] = downtime.message_to_users
        return service, status

    response = dict(map(service_availability, (service for service, _ in SERVICES)))
    response['*'] = {'status': all(status['status'] for status in response.values())}
    return JsonResponse(response)


class NotificationView(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = ()

    def get_queryset(self):
        return Notification.objects.exclude(end__lt=timezone.now())

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(public=True)
        target_filter = self.request.GET.get('target__startswith')
        if target_filter:
            queryset = queryset.filter(target__startswith=target_filter)
        return queryset
