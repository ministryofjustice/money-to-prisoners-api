from django.conf import settings
from django.forms import MediaDefiningClass
from django.http.request import QueryDict
from django.utils.text import re_camel_case
from django.utils.translation import gettext_lazy as _

from core.views import DashboardView


class DashboardModule(metaclass=MediaDefiningClass):
    template = 'core/dashboard/module.html'
    column_count = 1
    html_classes = ''
    title = _('Dashboard')
    show_stand_out = False
    enabled = True
    priority = 0
    cookie_key = None

    def __init__(self, dashboard_view):
        self.dashboard_view = dashboard_view
        self.cookie_data = QueryDict(dashboard_view.cookie_data.get(self.cookie_key)) or None

    @property
    def html_id(self):
        html_id = re_camel_case.sub(r'_\1', self.__class__.__name__)
        html_id = html_id.strip().lower()
        return 'id' + html_id


@DashboardView.register_dashboard
class ExternalDashboards(DashboardModule):
    template = 'core/dashboard/external-dashboards.html'
    column_count = 2
    title = _('External dashboards and logs')
    apps = [
        'api', 'cashbook', 'bank-admin', 'noms-ops',
        'transaction-uploader', 'send-money',
    ]
    grafana_host = None
    kibana_host = None
    sentry_url = None
    sensu_url = None
    kibana_params = '_g=(time:(from:now-24h,mode:quick,to:now))'  # last 24 hours

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if settings.ENVIRONMENT == 'test':
            self.grafana_host = 'grafana-staging.service.dsd.io'
            self.kibana_host = 'kibana-staging.service.dsd.io'
            self.sentry_url = 'https://sentry.service.dsd.io/mojds/mtp-test-%(app)s/'
            self.sensu_url = 'https://sensu-staging.service.dsd.io/#/checks?q=moneytoprisoners'
        elif settings.ENVIRONMENT == 'prod':
            self.grafana_host = 'grafana.service.dsd.io'
            self.kibana_host = 'kibana.service.dsd.io'
            self.sentry_url = 'https://sentry.service.dsd.io/mojds/mtp-prod-%(app)s/'
            self.sensu_url = 'https://sensu.service.dsd.io/#/checks?q=moneytoprisoners'

        self.enabled = self.kibana_host or self.grafana_host or self.sentry_url or self.sensu_url

    def get_table(self):
        table = []
        if self.kibana_host:
            table.append({
                'title': _('Application dashboard'),
                'links': [
                    {
                        'title': _('All apps'),
                        'url': 'https://%s/#/dashboard/MTP?%s' % (self.kibana_host, self.kibana_params)
                    }
                ],
            })
            table.append({
                'title': _('Application logs'),
                'links': self.make_app_links('https://%(kibana_host)s/#/discover/MTP-%(app)s'
                                             '?%(kibana_params)s'),
            })
        if self.sentry_url:
            table.append({
                'title': _('Sentry error monitors'),
                'links': self.make_app_links(self.sentry_url),
            })
        if self.sensu_url:
            table.append({
                'title': _('Sensu monitoring checks'),
                'links': [
                    {
                        'title': _('All apps'),
                        'url': self.sensu_url
                    }
                ]
            })
        if self.grafana_host:
            table.append({
                'title': _('Host machine dashboards'),
                'links': self.make_app_links('https://%(grafana_host)s/dashboard/db/mtp'
                                             '?var-project=moneytoprisoners-%(app)s'),
            })
        return table

    def make_app_links(self, link_template):
        return [
            {
                'title': app,
                'url': link_template % {
                    'grafana_host': self.grafana_host,
                    'kibana_host': self.kibana_host,
                    'kibana_params': self.kibana_params,
                    'app': app,
                }
            }
            for app in self.apps
        ]
