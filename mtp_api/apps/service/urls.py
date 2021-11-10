from django.conf.urls import include, url
from rest_framework import routers

from service.views import NotificationView, service_availability_view

router = routers.DefaultRouter()
router.register(r'notifications', NotificationView, basename='notifications')

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^service-availability/$', service_availability_view),
]
