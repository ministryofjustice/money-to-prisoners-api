from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView
from moj_irat.views import HealthcheckView, PingJsonView
from mtp_common.metrics.views import metrics_view

from .views import schema_view


urlpatterns = [
    url(r'^', include('prison.urls')),
    url(r'^', include('mtp_auth.urls')),
    url(r'^', include('transaction.urls')),
    url(r'^', include('account.urls')),
    url(r'^', include('payment.urls')),
    url(r'^', include('credit.urls')),
    url(r'^', include('security.urls')),
    url(r'^', include('service.urls')),
    url(r'^', include('disbursement.urls')),
    url(r'^', include('core.urls')),
    url(r'^', include('notification.urls')),
    url(r'^', include('performance.urls')),

    url(r'^oauth2/', include(('oauth2_provider.urls', 'oauth2_provider'), namespace='oauth2_provider')),
    url(r'^admin/', admin.site.urls),
    url(r'^admin/', include('django.conf.urls.i18n')),
    url(r'^ping.json$', PingJsonView.as_view(
        build_date_key='APP_BUILD_DATE',
        commit_id_key='APP_GIT_COMMIT',
        version_number_key='APP_BUILD_TAG',
    ), name='ping_json'),
    url(r'^healthcheck.json$', HealthcheckView.as_view(), name='healthcheck_json'),
    url(r'^metrics.txt$', metrics_view, name='prometheus_metrics'),

    url(r'^favicon.ico$', RedirectView.as_view(url=settings.STATIC_URL + 'images/favicon.ico', permanent=True)),
    url(r'^robots.txt$', lambda request: HttpResponse('User-agent: *\nDisallow: /', content_type='text/plain')),
    url(r'^\.well-known/security\.txt$', RedirectView.as_view(
        url='https://raw.githubusercontent.com/ministryofjustice/security-guidance'
            '/main/contact/vulnerability-disclosure-security.txt',
        permanent=True,
    )),

    url(r'^404.html$', lambda request: HttpResponse(
        _('Page not found'),
        content_type='text/plain', status=404,
    )),
    url(r'^500.html$', lambda request: HttpResponse(
        _('Sorry, something went wrong'),
        content_type='text/plain', status=500,
    )),

    url(r'^$', lambda request: HttpResponse(content_type='text/plain', status=204)),
]
if settings.ENVIRONMENT in ('test', 'local'):
    urlpatterns.extend([
        url(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
        url(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
        url(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    ])
