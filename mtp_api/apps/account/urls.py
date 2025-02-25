from django.urls import include, re_path
from rest_framework import routers

from account import views

router = routers.DefaultRouter()
router.register(r'balances', views.BalanceView)

urlpatterns = [
    re_path(r'^', include(router.urls)),
]
