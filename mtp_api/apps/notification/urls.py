from django.conf.urls import url, include

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'subscriptions', views.SubscriptionView)
router.register(r'events', views.EventView)

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^rules/$', views.RuleView.as_view(), name='rule-list'),
]
