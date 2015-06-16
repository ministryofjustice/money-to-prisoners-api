from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.views.generic.base import TemplateView

from rest_framework.routers import DefaultRouter

from transaction.views import TransactionView

router = DefaultRouter()
router.register(r'transactions', TransactionView)


urlpatterns = patterns('',
    url(r'^', include(router.urls)),
    url(r'^$', TemplateView.as_view(template_name='core/index.html')),

    url(r'^admin/', include(admin.site.urls)),
)
