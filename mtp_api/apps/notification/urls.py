from django.conf.urls import url, include
from rest_framework import routers

from notification import views

router = routers.DefaultRouter()
router.register(r'events', views.EventView)
router.register(r'emailpreferences', views.EmailPreferencesView, basename='emailpreferences')

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^rules/$', views.RuleView.as_view(), name='rule-list'),
]
