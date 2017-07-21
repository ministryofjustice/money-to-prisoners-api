from django.conf.urls import include, url
from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'roles', views.RoleViewSet)

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^change_password/$', views.ChangePasswordView.as_view(),
        name='user-change-password'),
    url(r'^change_password/(?P<code>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/$',
        views.ChangePasswordWithCodeView.as_view(),
        name='user-change-password-with-code'),
    url(r'^reset_password/$', views.ResetPasswordView.as_view(),
        name='user-reset-password'),
]
