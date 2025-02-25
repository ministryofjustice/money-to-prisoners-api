from django.views.decorators.csrf import csrf_exempt
from django.urls import include, re_path
from rest_framework_nested import routers

from credit import views

router = routers.DefaultRouter()
router.register(r'comments', views.CommentView)
router.register(r'batches', views.ProcessingBatchView)

batch_router = routers.SimpleRouter()
batch_router.register(r'private-estate-batches', views.PrivateEstateBatchView)
batch_credits_router = routers.NestedSimpleRouter(batch_router, r'private-estate-batches', lookup='batch')
batch_credits_router.register(r'credits', views.PrivateEstateBatchCreditsView, basename='privateestatebatch-credit')

urlpatterns = [
    re_path(r'^credits/$', csrf_exempt(views.GetCredits.as_view({'get': 'list'}, suffix='List')), name='credit-list'),
    re_path(r'^credits/actions/review/$', views.ReviewCredits.as_view(actions={'post': 'review'}), name='credit-review'),
    re_path(r'^credits/actions/credit/$', views.CreditCredits.as_view(actions={'post': 'credit'}), name='credit-credit'),
    re_path(
        r'^credits/actions/setmanual/$',
        views.SetManualCredits.as_view(actions={'post': 'credit'}),
        name='setmanual-credit'
    ),
    re_path(r'^credits/processed/$', views.CreditsGroupedByCreditedList.as_view(), name='credit-processed-list'),
    re_path(r'^credits/', include(router.urls)),

    re_path(r'^', include(batch_router.urls)),
    re_path(r'^', include(batch_credits_router.urls)),
]
