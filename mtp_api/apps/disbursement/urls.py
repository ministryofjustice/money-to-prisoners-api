from django.conf.urls import url, include

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'disbursements', views.DisbursementView)
router.register(r'recipients', views.RecipientView)

urlpatterns = [
    url(r'^disbursements/actions/reject/$',
        views.RejectDisbursementsView.as_view(), name='disbursement-reject'),
    url(r'^disbursements/actions/confirm/$',
        views.ConfirmDisbursementsView.as_view(), name='disbursement-confirm'),
    url(r'^disbursements/actions/send/$',
        views.SendDisbursementsView.as_view(), name='disbursement-send'),
    url(r'^', include(router.urls)),
]
