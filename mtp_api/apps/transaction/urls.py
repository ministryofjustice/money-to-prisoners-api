from django.conf.urls import patterns, url, include

from rest_framework import routers

from .api.cashbook.routers import TransactionRouter
from .api.cashbook import views as cashbook_views
from .api.bank_admin import views as bank_admin_views


cashbook_transaction_router = TransactionRouter()
cashbook_transaction_router.register(r'transactions', cashbook_views.TransactionView)

admin_transaction_router = routers.DefaultRouter()
admin_transaction_router.register(r'transactions', bank_admin_views.TransactionView)

urlpatterns = patterns('',
    url(r'^bank-admin/', include(admin_transaction_router.urls, namespace='bank-admin')),
    url(r'^cashbook/', include(cashbook_transaction_router.urls, namespace='cashbook')),
)
