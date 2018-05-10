from django.conf.urls import url, include

from rest_framework import routers

from core import views

router = routers.DefaultRouter()
router.register(r'file-downloads', views.FileDownloadView)
router.register(r'tokens', views.TokenView)

urlpatterns = [
    url(
        r'^file-downloads/missing/$',
        views.MissingFileDownloadView.as_view(),
        name='filedownload-missing'
    ),
    url(r'^', include(router.urls)),
]
