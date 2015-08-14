from django.conf.urls import patterns, url, include

from rest_framework import routers

from .routers import TransactionRouter
from . import views


transaction_router = TransactionRouter()

admin_transaction_router = routers.DefaultRouter()
admin_transaction_router.register(r'transactions', views.AdminTransactionView)

urlpatterns = patterns('',
    url(r'^bank-admin/', include(admin_transaction_router.urls, namespace='bank-admin')),
    url(r'^', include(transaction_router.urls)),
)
