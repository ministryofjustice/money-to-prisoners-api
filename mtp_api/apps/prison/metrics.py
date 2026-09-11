from django.apps import apps
from prometheus_client import Counter

prisoner_validity_checks = Counter(
    'mtp_prisoner_validity_checks', 'Prisoner validity checks made from the public send-money service',
    labelnames=('outcome', 'pid'),
)
try:
    app = apps.get_app_config('metrics')
    app.register_collector(prisoner_validity_checks)
except LookupError:
    pass
