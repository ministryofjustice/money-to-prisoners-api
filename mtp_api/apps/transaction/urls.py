from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^transactions/$', views.TransactionView.as_view({
        'get': 'list',
        'post': 'create',
        'patch': 'patch_processed'
        }), name='transaction-list'),
    url(r'^transactions/reconcile/$', views.ReconcileTransactionsView.as_view(),
        name='reconcile-transactions')
]
