from django.urls import include, re_path
from rest_framework import routers

from notification import views

router = routers.DefaultRouter()
router.register(r'events', views.EventView)

urlpatterns = [
    re_path(r'^emailpreferences/$', views.EmailPreferencesView.as_view(), name='email-preferences'),
    re_path(r'^events/pages/$', views.EventPagesView.as_view(), name='event-pages'),
    re_path(r'^rules/$', views.RuleView.as_view(), name='rule-list'),
    re_path(r'^', include(router.urls)),
]
