from django.conf.urls import patterns, url, include

from .api.cashbook import urls as cashbook_urls
from .api.bank_admin import urls as bank_admin_urls


urlpatterns = patterns('',
    url(r'^bank_admin/', include(bank_admin_urls, namespace='bank_admin')),
    url(r'^cashbook/', include(cashbook_urls, namespace='cashbook')),
)
