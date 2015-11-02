from django.conf.urls import patterns, url, include

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'files', views.FileView)
router.register(r'file_types', views.FileTypeView)

urlpatterns = patterns('',
    url(r'^', include(router.urls)),
)
