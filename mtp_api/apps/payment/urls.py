from django.conf.urls import url, include
from rest_framework import routers

from payment import views

router = routers.DefaultRouter()
router.register(r'payments', views.PaymentView)
router.register(r'batches', views.BatchView)

urlpatterns = [
    url(r'^', include(router.urls)),
]
