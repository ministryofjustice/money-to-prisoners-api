from django.conf.urls import url

from .views import RecreateTestDataView

app_name = 'mtp-admin'
urlpatterns = [
    url(r'^recreate-test-data/$', RecreateTestDataView.as_view(), name='recreate_test_data'),
]
