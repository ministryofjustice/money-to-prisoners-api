from django.conf.urls import patterns, url, include

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'prisoner-locations', views.PrisonerLocationView)

urlpatterns = patterns('',
    url(r'^', include(router.urls)),
)
