from django.conf.urls import url

from . import view_dashboard

urlpatterns = [
     url(r'^performance-dashboard/$', view_dashboard.PerformanceDashboardView.as_view(), name='performance_dashboard'),
]
