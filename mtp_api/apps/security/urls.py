from django.conf.urls import url, include

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'senders', views.SenderProfileView)
router.register(r'prisoners', views.PrisonerProfileView)

urlpatterns = [
    url(r'^', include(router.urls)),
]
