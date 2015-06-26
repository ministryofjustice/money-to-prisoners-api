from django.conf.urls import patterns, include, url
from django.contrib import admin

from django.views.generic.base import TemplateView

from core.router import TransactionRouter

router = TransactionRouter()

urlpatterns = patterns('',
    url(r'^', include(router.urls)),
    url(r'^$', TemplateView.as_view(template_name='core/index.html')),
    url(r'^oauth2/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    url(r'^docs/', include('rest_framework_swagger.urls')),
    url(r'^admin/', include(admin.site.urls)),
)
