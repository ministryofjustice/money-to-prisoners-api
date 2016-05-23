import json
import math

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.forms import MediaDefiningClass
from django.http.request import QueryDict
from django.utils.safestring import mark_safe
from django.utils.text import re_camel_case
from django.utils.translation import gettext, gettext_lazy as _
import requests

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


@DashboardView.register_dashboard
class SatisfactionDashboard(DashboardModule):
    template = 'core/dashboard/satisfaction-results.html'
    column_count = 1
    title = _('User satisfaction')
    cache_lifetime = 60 * 60  # 1 hour
    survey_id = '2527768'  # results: http://data.surveygizmo.com/r/413845_57330cc99681a7.27709426
    questions = [
        {'id': '13', 'title': _('Easiness'), 'reverse': False},
        {'id': '14', 'title': _('Speed'), 'reverse': True},
        {'id': '15', 'title': _('Cost'), 'reverse': False},
        {'id': '70', 'title': _('Quality'), 'reverse': False},
    ]

    class Media:
        css = {
            'all': ('core/css/satisfaction-results.css',)
        }
        js = (
            'https://www.gstatic.com/charts/loader.js',
            'core/js/google-charts.js',
            'core/js/satisfaction-results.js',
        )

    def __init__(self, dashboard_view):
        super().__init__(dashboard_view)
        self.enabled = bool(settings.SURVEY_GIZMO_API_KEY)
        self.cache_key = 'satisfaction_results'

        self.max_response_count = 0

    def get_satisfaction_results(self):
        response = cache.get(self.cache_key)
        if not response:
            url_prefix = 'https://restapi.surveygizmo.com/v4/survey/%s' % self.survey_id

            response = []
            for question in self.questions:
                question_id = question['id']
                question_response = requests.get('%(url_prefix)s/surveyquestion/%(question)s' % {
                    'url_prefix': url_prefix,
                    'question': question_id,
                }, params={
                    'api_token': settings.SURVEY_GIZMO_API_KEY,
                }).json()['data']
                statistics_response = requests.get('%(url_prefix)s/surveystatistic' % {
                    'url_prefix': url_prefix,
                }, params={
                    'api_token': settings.SURVEY_GIZMO_API_KEY,
                    'surveyquestion': question_id,
                }).json()['data']
                response.append({
                    'id': question_id,
                    'question': question_response,
                    'statistics': statistics_response,
                })

            cache.set(self.cache_key, response, timeout=self.cache_lifetime)

        return response

    def get_chart_data(self):
        responses = self.get_satisfaction_results()

        columns = [
            {'type': 'string', 'label': gettext('Quality'), 'role': 'domain'},
            {'type': 'number', 'label': gettext('Very dissatisfied'), 'role': 'data'},
            {'type': 'string', 'role': 'annotation'},
            {'type': 'number', 'label': gettext('Dissatisfied'), 'role': 'data'},
            {'type': 'string', 'role': 'annotation'},
            {'type': 'number', 'label': gettext('Ambivalent'), 'role': 'data'},
            {'type': 'string', 'role': 'annotation'},
            {'type': 'number', 'label': gettext('Satisfied'), 'role': 'data'},
            {'type': 'string', 'role': 'annotation'},
            {'type': 'number', 'label': gettext('Very satisfied'), 'role': 'data'},
            {'type': 'string', 'role': 'annotation'},
            {'type': 'number', 'label': gettext('Not applicable'), 'role': 'data'},
            {'type': 'string', 'role': 'annotation'},
        ]
        rows = []
        max_response_sum = 0
        for question_index, question in enumerate(responses):
            response_sum = 0
            definition = self.questions[question_index]
            row = [str(definition['title'])]
            options = question['question']['options']
            if definition['reverse']:
                options = list(reversed(options[:-1])) + [options[-1]]
            if len(options) != 6:
                messages.error(
                    self.dashboard_view.request,
                    _('Satisfaction survey question %s have unexpected numbers of options' % question['id'])
                )
                return
            if options[-1]['value'] != 'Not applicable':
                messages.error(
                    self.dashboard_view.request,
                    _('Satisfaction survey question %s do not all have "Not applicable" option' % question['id'])
                )
                return
            max_count = 0
            max_count_index = None
            for option_index, option in enumerate(options):
                title = option['value']
                option_votes = 0
                for result in question['statistics']['Breakdown']:
                    if result['label'] == title:
                        option_votes = int(result['count'])
                        break
                row.append(option_votes)
                row.append(None)
                if option_votes > max_count:
                    max_count = option_votes
                    max_count_index = option_index
                response_sum += option_votes
            if max_count_index is not None:
                row[(max_count_index + 1) * 2] = str(math.ceil(100 * max_count / response_sum)) + '%'
            rows.append(row)
            if response_sum > max_response_sum:
                max_response_sum = response_sum

        return mark_safe(json.dumps({
            'columns': columns,
            'rows': rows,
            'max': math.ceil(max_response_sum / 10) * 10,
        }))
