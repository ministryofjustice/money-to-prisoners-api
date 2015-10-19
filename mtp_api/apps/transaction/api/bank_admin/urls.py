from django.conf.urls import patterns, url

from . import views

urlpatterns = patterns('',
    url(r'^transactions/$', views.TransactionView.as_view({
        'get': 'list',
        'post': 'create',
        'patch': 'patch_processed'
    }), name='transaction-list'),
)
