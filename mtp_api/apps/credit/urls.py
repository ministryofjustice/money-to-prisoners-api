from django.conf.urls import url, include
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers

from . import views as views

router = routers.DefaultRouter()
router.register(r'comments', views.CommentView)

urlpatterns = [
    url(r'^credits/$', csrf_exempt(views.CreditList.as_view()), name='credit-list'),
    url(r'^credits/locked/$', views.LockedCreditList.as_view(), name='credit-locked'),
    url(r'^credits/actions/lock/$', views.LockCredits.as_view(), name='credit-lock'),
    url(r'^credits/actions/unlock/$', views.UnlockCredits.as_view(), name='credit-unlock'),
    url(r'^credits/senders/$', csrf_exempt(views.SenderList.as_view()), name='sender-list'),
    url(r'^credits/prisoners/$', csrf_exempt(views.PrisonerList.as_view()), name='prisoner-list'),
    url(r'^credits/', include(router.urls)),
]
