from django.conf.urls import url

from transaction import views

urlpatterns = [
    url(r'^transactions/$', views.TransactionView.as_view({
        'get': 'list',
        'post': 'create',
        'patch': 'patch_processed',
    }), name='transaction-list'),
    url(
        r'^transactions/reconcile/$',
        views.ReconcileTransactionsView.as_view(actions={'post': 'patch_processed'}),
        name='reconcile-transactions'
    ),
]
