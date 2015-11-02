from django.conf.urls import patterns, url

from .views import RecreateTestDataView

urlpatterns = patterns('',
    url(r'^recreate-test-data/$', RecreateTestDataView.as_view(), name='recreate_test_data'),
)
