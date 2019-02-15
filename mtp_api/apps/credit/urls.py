from django.conf.urls import url, include
from django.views.decorators.csrf import csrf_exempt
from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'comments', views.CommentView)
router.register(r'batches', views.ProcessingBatchView)

urlpatterns = [
    url(r'^credits/$', csrf_exempt(views.GetCredits.as_view({'get': 'list'}, suffix='List')), name='credit-list'),
    url(r'^credits/actions/review/$', views.ReviewCredits.as_view(), name='credit-review'),
    url(r'^credits/actions/credit/$', views.CreditCredits.as_view(), name='credit-credit'),
    url(r'^credits/actions/setmanual/$', views.SetManualCredits.as_view(), name='setmanual-credit'),
    url(r'^credits/processed/$', views.CreditsGroupedByCreditedList.as_view(), name='credit-processed-list'),
    url(r'^credits/', include(router.urls)),
    url(r'^private-estate-batches/$', views.PrivateEstateBatchView.as_view({'get': 'list'}),
        name='private-estate-batch-list'),
]
