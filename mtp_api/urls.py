from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, re_path
from django.utils.translation import gettext_lazy as _
from django.views.generic import RedirectView
from moj_irat.views import HealthcheckView, PingJsonView
from mtp_common.metrics.views import metrics_view

from .views import schema_view

urlpatterns = [
    re_path(r'^', include('prison.urls')),
    re_path(r'^', include('mtp_auth.urls')),
    re_path(r'^', include('transaction.urls')),
    re_path(r'^', include('account.urls')),
    re_path(r'^', include('payment.urls')),
    re_path(r'^', include('credit.urls')),
    re_path(r'^', include('security.urls')),
    re_path(r'^', include('service.urls')),
    re_path(r'^', include('disbursement.urls')),
    re_path(r'^', include('core.urls')),
    re_path(r'^', include('notification.urls')),
    re_path(r'^', include('performance.urls')),

    re_path(r'^oauth2/', include(('mtp_auth.urls_oauth2', 'oauth2_provider'), namespace='oauth2_provider')),

    re_path(r'^admin/', admin.site.urls),
    re_path(r'^admin/', include('django.conf.urls.i18n')),

    re_path(r'^ping.json$', PingJsonView.as_view(
        build_date_key='APP_BUILD_DATE',
        commit_id_key='APP_GIT_COMMIT',
        version_number_key='APP_BUILD_TAG',
    ), name='ping_json'),
    re_path(r'^healthcheck.json$', HealthcheckView.as_view(), name='healthcheck_json'),
    re_path(r'^metrics.txt$', metrics_view, name='prometheus_metrics'),

    re_path(r'^favicon.ico$', RedirectView.as_view(url=settings.STATIC_URL + 'images/favicon.ico', permanent=True)),
    re_path(r'^robots.txt$', lambda request: HttpResponse('User-agent: *\nDisallow: /', content_type='text/plain')),
    re_path(r'^\.well-known/security\.txt$', RedirectView.as_view(
        url='https://security-guidance.service.justice.gov.uk/.well-known/security.txt',
        permanent=True,
    )),

    re_path(r'^404.html$', lambda request: HttpResponse(
        _('Page not found'),
        content_type='text/plain', status=404,
    )),
    re_path(r'^500.html$', lambda request: HttpResponse(
        _('Sorry, something went wrong'),
        content_type='text/plain', status=500,
    )),

    re_path(r'^$', lambda request: HttpResponse(content_type='text/plain', status=204)),
]

if settings.ENVIRONMENT != 'prod':
    urlpatterns.extend([
        re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
        re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
        re_path(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    ])
