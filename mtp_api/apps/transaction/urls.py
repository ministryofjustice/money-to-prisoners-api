from django.conf.urls import include, url

from .api.cashbook import urls as cashbook_urls
from .api.bank_admin import urls as bank_admin_urls
from .api.send_money import urls as send_money_urls

urlpatterns = [
    url(r'^bank_admin/', include(bank_admin_urls, namespace='bank_admin')),
    url(r'^cashbook/', include(cashbook_urls, namespace='cashbook')),
    url(r'^send_money/', include(send_money_urls, namespace='send_money')),
]
