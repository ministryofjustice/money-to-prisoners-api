from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponse
from django.views.generic import RedirectView

from moj_irat.views import HealthcheckView, PingJsonView

urlpatterns = [
    url(r'^', include('prison.urls')),
    url(r'^', include('mtp_auth.urls')),
    url(r'^', include('transaction.urls')),
    url(r'^', include('account.urls')),
    url(r'^', include('payment.urls')),

    url(r'^oauth2/', include(('oauth2_provider.urls', 'oauth2_provider'), namespace='oauth2_provider')),
    url(r'^docs/', include('rest_framework_swagger.urls')),
    url(r'^admin/', admin.site.urls),

    url(r'^ping.json$', PingJsonView.as_view(
        build_date_key='APP_BUILD_DATE',
        commit_id_key='APP_GIT_COMMIT',
        version_number_key='APP_BUILD_TAG',
    ), name='ping_json'),
    url(r'^healthcheck.json$', HealthcheckView.as_view(), name='healthcheck_json'),

    url(r'^favicon.ico$', RedirectView.as_view(url=settings.STATIC_URL + 'images/favicon.ico', permanent=True)),
    url(r'^robots.txt$', lambda request: HttpResponse('User-agent: *\nDisallow: /', content_type='text/plain')),
]
