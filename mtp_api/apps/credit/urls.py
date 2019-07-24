from django.conf.urls import url, include
from django.views.decorators.csrf import csrf_exempt
from rest_framework_nested import routers

from credit import views

router = routers.DefaultRouter()
router.register(r'comments', views.CommentView)
router.register(r'batches', views.ProcessingBatchView)

batch_router = routers.SimpleRouter()
batch_router.register(r'private-estate-batches', views.PrivateEstateBatchView)
batch_credits_router = routers.NestedSimpleRouter(batch_router, r'private-estate-batches', lookup='batch')
batch_credits_router.register(r'credits', views.PrivateEstateBatchCreditsView, base_name='privateestatebatch-credit')

urlpatterns = [
    url(r'^credits/$', csrf_exempt(views.GetCredits.as_view({'get': 'list'}, suffix='List')), name='credit-list'),
    url(r'^credits/actions/review/$', views.ReviewCredits.as_view(), name='credit-review'),
    url(r'^credits/actions/credit/$', views.CreditCredits.as_view(), name='credit-credit'),
    url(r'^credits/actions/setmanual/$', views.SetManualCredits.as_view(), name='setmanual-credit'),
    url(r'^credits/processed/$', views.CreditsGroupedByCreditedList.as_view(), name='credit-processed-list'),
    url(r'^credits/', include(router.urls)),

    url(r'^', include(batch_router.urls)),
    url(r'^', include(batch_credits_router.urls)),
]
