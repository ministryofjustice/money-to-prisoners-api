from django.conf.urls import url

from .views import RecreateTestDataView

urlpatterns = [
    url(r'^recreate-test-data/$', RecreateTestDataView.as_view(), name='recreate_test_data'),
]
