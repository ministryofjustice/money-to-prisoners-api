from django.conf.urls import include, url
from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r'prisoner_locations', views.PrisonerLocationView)
router.register(r'prisoner_validity', views.PrisonerValidityView,
                base_name='prisoner_validity')
router.register(r'prisons', views.PrisonView, base_name='prison')

urlpatterns = [
    url(r'^', include(router.urls)),
]
