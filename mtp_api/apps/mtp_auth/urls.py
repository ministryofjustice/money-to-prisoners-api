from django.urls import include, re_path
from rest_framework_nested import routers

from mtp_auth import views

router = routers.DefaultRouter()
router.register(r'users', views.UserViewSet)
user_router = routers.NestedSimpleRouter(router, r'users', lookup='user')
user_router.register(r'flags', views.UserFlagViewSet, basename='user-flags')
router.register(r'roles', views.RoleViewSet)
router.register(r'requests', views.AccountRequestViewSet)
router.register(r'job-information', views.JobInformationViewSet, basename='job-information')

urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^', include(user_router.urls)),
    re_path(r'^change_password/$', views.ChangePasswordView.as_view(),
        name='user-change-password'),
    re_path(r'^change_password/(?P<code>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/$',
        views.ChangePasswordWithCodeView.as_view(),
        name='user-change-password-with-code'),
    re_path(r'^reset_password/$', views.ResetPasswordView.as_view(),
        name='user-reset-password'),
]
