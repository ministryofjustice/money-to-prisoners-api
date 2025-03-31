from django.urls import include, re_path
from rest_framework import routers

from service.views import NotificationView, service_availability_view

router = routers.DefaultRouter()
router.register(r'notifications', NotificationView, basename='notifications')

urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^service-availability/$', service_availability_view),
]
