from django.conf.urls import patterns, url
from django.views.decorators.csrf import csrf_exempt

from . import views as views


urlpatterns = patterns('',
    url(r'^transactions/$', csrf_exempt(views.TransactionList.as_view()), name='transaction-list'),
    url(r'^transactions/actions/lock/$', views.LockTransactions.as_view(), name='transaction-lock'),
    url(r'^transactions/actions/unlock/$', views.UnlockTransactions.as_view(), name='transaction-unlock'),
)
