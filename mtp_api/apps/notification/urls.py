from django.conf.urls import url, include
from rest_framework import routers

from notification import views

router = routers.DefaultRouter()
router.register(r'events', views.EventView)

urlpatterns = [
    url(r'^emailpreferences/$', views.EmailPreferencesView.as_view(), name='email-preferences'),
    url(r'^events/pages/$', views.EventPagesView.as_view(), name='event-pages'),
    url(r'^rules/$', views.RuleView.as_view(), name='rule-list'),
    url(r'^', include(router.urls)),
]
