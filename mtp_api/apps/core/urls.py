from django.urls import include, re_path
from rest_framework import routers

from core import views

router = routers.DefaultRouter()
router.register(r'file-downloads', views.FileDownloadView)

urlpatterns = [
    re_path(
        r'^file-downloads/missing/$',
        views.MissingFileDownloadView.as_view(),
        name='filedownload-missing',
    ),
    re_path(r'^', include(router.urls)),
]
