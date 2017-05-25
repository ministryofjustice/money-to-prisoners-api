from django.conf.urls import url, include
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers

from . import views as views

router = routers.DefaultRouter()
router.register(r'comments', views.CommentView)
router.register(r'batches', views.ProcessingBatchView)

urlpatterns = [
    url(r'^credits/$', csrf_exempt(views.CreditList.as_view()), name='credit-list'),
    url(r'^credits/locked/$', views.LockedCreditList.as_view(), name='credit-locked'),
    url(r'^credits/actions/lock/$', views.LockCredits.as_view(), name='credit-lock'),
    url(r'^credits/actions/unlock/$', views.UnlockCredits.as_view(), name='credit-unlock'),
    url(r'^credits/actions/review/$', views.ReviewCredits.as_view(), name='credit-review'),
    url(r'^credits/actions/credit/$', views.CreditCredits.as_view(), name='credit-credit'),
    url(r'^credits/actions/setmanual/$', views.SetManualCredits.as_view(), name='setmanual-credit'),
    url(r'^credits/', include(router.urls)),
]
