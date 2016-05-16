from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt

from . import views as views

urlpatterns = [
    url(r'^credits/$', csrf_exempt(views.CreditList.as_view()), name='credit-list'),
    url(r'^credits/locked/$', views.LockedCreditList.as_view(), name='credit-locked'),
    url(r'^credits/actions/lock/$', views.LockCredits.as_view(), name='credit-lock'),
    url(r'^credits/actions/unlock/$', views.UnlockCredits.as_view(), name='credit-unlock'),
    url(r'^credits/senders/$', csrf_exempt(views.SenderList.as_view()), name='sender-list'),
]
