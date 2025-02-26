from django.urls import include, re_path
from rest_framework import routers

from disbursement import views

router = routers.DefaultRouter()
router.register(r'disbursements/comments', views.CommentView)
router.register(r'disbursements', views.DisbursementView)

urlpatterns = [
    re_path(
        r'^disbursements/actions/reject/$',
        views.RejectDisbursementsView.as_view(),
        name='disbursement-reject',
    ),
    re_path(
        r'^disbursements/actions/preconfirm/$',
        views.PreConfirmDisbursementsView.as_view(),
        name='disbursement-preconfirm',
    ),
    re_path(
        r'^disbursements/actions/reset/$',
        views.ResetDisbursementsView.as_view(),
        name='disbursement-reset',
    ),
    re_path(
        r'^disbursements/actions/confirm/$',
        views.ConfirmDisbursementsView.as_view(),
        name='disbursement-confirm',
    ),
    re_path(
        r'^disbursements/actions/send/$',
        views.SendDisbursementsView.as_view(),
        name='disbursement-send',
    ),
    re_path(r'^', include(router.urls)),
]
