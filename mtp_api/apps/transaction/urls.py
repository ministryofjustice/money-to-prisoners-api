from django.urls import re_path

from transaction import views

urlpatterns = [
    re_path(r'^transactions/$', views.TransactionView.as_view({
        'get': 'list',
        'post': 'create',
        'patch': 'patch_processed',
    }), name='transaction-list'),
    re_path(
        r'^transactions/reconcile/$',
        views.ReconcileTransactionsView.as_view(actions={'post': 'patch_processed'}),
        name='reconcile-transactions'
    ),
]
