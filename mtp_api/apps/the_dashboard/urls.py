from django.conf.urls import url

from . import views

urlpatterns = [
     url(r'^dashboard/$', views.DashboardView.as_view(), name='dashboard'),
     # url(r'^dashboard_two/$', view_two.DashboardTwoView.as_view(), name='dashboard_two'),
]
