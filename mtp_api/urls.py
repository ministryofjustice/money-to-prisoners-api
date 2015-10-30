from django.conf.urls import patterns, include, url
from django.contrib import admin

admin.site.index_template = 'core/index.html'

urlpatterns = patterns(
    '',
    url(r'^', include('prison.urls')),
    url(r'^', include('mtp_auth.urls')),
    url(r'^', include('transaction.urls')),
    url(r'^', include('account.urls')),

    url(r'^oauth2/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    url(r'^docs/', include('rest_framework_swagger.urls')),
    url(r'^admin/core/', include('core.urls', namespace='mtp-admin')),
    url(r'^admin/', include(admin.site.urls)),
)
