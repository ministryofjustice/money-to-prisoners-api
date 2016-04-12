from django.conf.urls import include, url
from django.contrib import admin

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
]
