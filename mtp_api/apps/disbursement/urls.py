from django.conf.urls import url, include

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'disbursements/comments', views.CommentView)
router.register(r'disbursements', views.DisbursementView)

urlpatterns = [
    url(r'^disbursements/actions/reject/$',
        views.RejectDisbursementsView.as_view(), name='disbursement-reject'),
    url(r'^disbursements/actions/preconfirm/$',
        views.PreConfirmDisbursementsView.as_view(), name='disbursement-preconfirm'),
    url(r'^disbursements/actions/reset/$',
        views.ResetDisbursementsView.as_view(), name='disbursement-reset'),
    url(r'^disbursements/actions/confirm/$',
        views.ConfirmDisbursementsView.as_view(), name='disbursement-confirm'),
    url(r'^disbursements/actions/send/$',
        views.SendDisbursementsView.as_view(), name='disbursement-send'),
    url(r'^', include(router.urls)),
]
