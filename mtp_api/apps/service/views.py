from django.http import JsonResponse

from service.models import Downtime, SERVICES


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
        return service, status

    response = dict(map(service_availability, (service for service, _ in SERVICES)))
    response['*'] = {'status': all(status['status'] for status in response.values())}
    return JsonResponse(response)
