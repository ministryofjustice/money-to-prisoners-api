from django.conf.urls import url

from service.views import service_availability_view

urlpatterns = [url(r'^service-availability/$', service_availability_view)]
