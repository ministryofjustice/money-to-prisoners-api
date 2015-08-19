from django.conf.urls import patterns, url, include

from rest_framework import routers

from .routers import CashbookTransactionRouter
from . import views


cashbook_transaction_router = CashbookTransactionRouter()
cashbook_transaction_router.register(r'transactions', views.CashbookTransactionView)

admin_transaction_router = routers.DefaultRouter()
admin_transaction_router.register(r'transactions', views.BankAdminTransactionView)

urlpatterns = patterns('',
    url(r'^bank-admin/', include(admin_transaction_router.urls, namespace='bank-admin')),
    url(r'^cashbook/', include(cashbook_transaction_router.urls, namespace='cashbook')),
)
