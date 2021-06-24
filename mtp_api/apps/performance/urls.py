from django.urls import path

from .views import PerformanceDataView


urlpatterns = [
    path('performance/data', PerformanceDataView.as_view(), name='performance-data'),
]
