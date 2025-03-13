from django.urls import include, re_path
from rest_framework import routers

from payment import views

router = routers.DefaultRouter()
router.register(r'payments', views.PaymentView)
router.register(r'batches', views.BatchView)

urlpatterns = [
    re_path(r'^', include(router.urls)),
]
