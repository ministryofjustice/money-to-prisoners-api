from django.conf.urls import patterns, url, include

from rest_framework import routers

from .api.cashbook import urls as cashbook_urls
from .api.bank_admin import views as bank_admin_views


admin_transaction_router = routers.DefaultRouter()
admin_transaction_router.register(r'transactions', bank_admin_views.TransactionView,
                                  base_name='transaction')

urlpatterns = patterns('',
    url(r'^bank_admin/', include(admin_transaction_router.urls, namespace='bank_admin')),
    url(r'^cashbook/', include(cashbook_urls, namespace='cashbook')),
)
