import logging

from django.conf import settings
from django.core.cache import cache
from django.forms import MediaDefiningClass
from django.http.request import QueryDict
from django.utils.text import re_camel_case
from django.utils.translation import gettext_lazy as _

from core.views import DashboardView

logger = logging.getLogger('mtp')


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
class GoogleAnalytics(DashboardModule):
    template = 'core/dashboard/google-analytics.html'
    title = _('Google Analytics')
    cache_lifetime = 60 * 60  # 1 hour
    reports = {
        'dev': [
            {'title': 'cashbook', 'tracking_id': 'UA-72467051-10', 'view_id': '115071201'},
            {'title': 'bank-admin', 'tracking_id': 'UA-72467051-4', 'view_id': '115055623'},
            {'title': 'prisoner-location-admin', 'tracking_id': 'UA-72467051-7', 'view_id': '115049733'},
            {'title': 'send-money', 'tracking_id': 'UA-72467051-1', 'view_id': '114873379'},
        ],
        'test': [
            {'title': 'cashbook', 'tracking_id': 'UA-72467051-11', 'view_id': '115036476'},
            {'title': 'bank-admin', 'tracking_id': 'UA-72467051-6', 'view_id': '115050938'},
            {'title': 'prisoner-location-admin', 'tracking_id': 'UA-72467051-8', 'view_id': '115033388'},
            {'title': 'send-money', 'tracking_id': 'UA-72467051-2', 'view_id': '114884357'},
        ],
        'prod': [
            {'title': 'cashbook', 'tracking_id': 'UA-72467051-12', 'view_id': '115023990'},
            {'title': 'bank-admin', 'tracking_id': 'UA-72467051-5', 'view_id': '115041582'},
            {'title': 'prisoner-location-admin', 'tracking_id': 'UA-72467051-9', 'view_id': '115033753'},
            {'title': 'send-money', 'tracking_id': 'UA-72467051-3', 'view_id': '114855672'},
            {'title': 'start-page', 'tracking_id': 'UA-72467051-13', 'view_id': '117845780'},
        ],
    }

    def __init__(self, start_date=None, end_date=None, **kwargs):
        super().__init__(**kwargs)
        if not start_date and not end_date:
            self.title = _('Google Analytics for yesterday')
        self.start_date = start_date or 'yesterday'
        self.end_date = end_date or 'yesterday'

        self.cache_key = 'dashboard_ga_report_%s_%s_%s' % (
            settings.ENVIRONMENT, hash(self.start_date), hash(self.end_date)
        )
        self.reports = self.reports.get(settings.ENVIRONMENT)
        self.enabled = settings.GOOGLE_API_KEY_PATH and self.reports

    def get_table(self):
        reports = self.get_reports()
        table = [[''] + [statistic['title'] for statistic in reports[0]['statistics']]]
        for report in reports:
            table.append([report['title']] + list(map(lambda statistic: statistic['value'],
                                                      report['statistics'])))
        return table

    def get_reports(self):
        from copy import deepcopy

        reports = cache.get(self.cache_key)
        if reports:
            return reports

        reports = deepcopy(self.reports)
        for report in reports:
            statistics = self.get_view_statistics(report['view_id'], [
                'ga:users', 'ga:sessions', 'ga:pageviews',
            ])
            report['statistics'] = [
                {
                    'title': _('Users'),
                    'value': statistics[0],
                },
                {
                    'title': _('Sessions'),
                    'value': statistics[1],
                },
                {
                    'title': _('Page views'),
                    'value': statistics[2],
                },
            ]

        cache.set(self.cache_key, reports, timeout=self.cache_lifetime)
        return reports

    def get_view_statistics(self, view_id, expressions):
        from apiclient import discovery
        from googleapiclient.errors import HttpError
        from httplib2 import Http
        from oauth2client.client import Error as OauthError
        from oauth2client.service_account import ServiceAccountCredentials

        discover_url = 'https://analyticsreporting.googleapis.com/$discovery/rest'
        scopes = ['https://www.googleapis.com/auth/analytics.readonly']

        try:
            credentials = ServiceAccountCredentials.from_json_keyfile_name(settings.GOOGLE_API_KEY_PATH,
                                                                           scopes=scopes)
            http_auth = credentials.authorize(Http())
            analytics = discovery.build('analyticsreporting', 'v4',
                                        discoveryServiceUrl=discover_url,
                                        http=http_auth)
            request = {
                'reportRequests': [{
                    'viewId': view_id,
                    'dateRanges': [{
                        'startDate': self.start_date,
                        'endDate': self.end_date,
                    }],
                    'metrics': [
                        {'expression': expression}
                        for expression in expressions
                    ]
                }]
            }
            request = analytics.reports().batchGet(body=request)
            response = request.execute()
            values = response['reports'][0]['data']['totals'][0]['values']
            return list(map(int, values))
        except (HttpError, OauthError, IndexError, KeyError, ValueError):
            logger.exception('Cannot load Google Analytics data')

        return [None for _ in expressions]


@DashboardView.register_dashboard
class ExternalDashboards(DashboardModule):
    template = 'core/dashboard/external-dashboards.html'
    column_count = 2
    title = _('External dashboards and logs')
    apps = [
        'api', 'cashbook', 'bank-admin', 'prisoner-location-admin',
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
