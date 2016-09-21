from moj_irat.healthchecks import HealthcheckResponse, registry

from service.models import Downtime, SERVICES


def get_service_downtime_healthcheck(service):
    def check_downtime():
        status = {'name': service, 'status': True}
        active_downtime = Downtime.objects.active_downtime(service)
        if active_downtime is not None:
            status['status'] = False
            if active_downtime.end is not None:
                status['downtime_end'] = active_downtime.end.isoformat()
        return HealthcheckResponse(**status)
    return check_downtime

for service, _ in SERVICES:
    registry.register_healthcheck(get_service_downtime_healthcheck(service))
