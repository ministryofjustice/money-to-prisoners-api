from django.conf.urls import include, url
from rest_framework import routers

from prison import views

router = routers.DefaultRouter()
router.register(r'prisoner_locations', views.PrisonerLocationView, base_name='prisonerlocation')
router.register(r'prisoner_validity', views.PrisonerValidityView,
                base_name='prisoner_validity')
router.register(r'prisons', views.PrisonView, base_name='prison')
router.register(r'prison_populations', views.PopulationView, base_name='prison_population')
router.register(r'prison_categories', views.CategoryView, base_name='prison_category')

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^prisoner_locations/actions/delete_old/$',
        views.DeleteOldPrisonerLocationsView.as_view(),
        name='prisonerlocation-delete-old'),
    url(r'^prisoner_locations/actions/delete_inactive/$',
        views.DeleteInactivePrisonerLocationsView.as_view(),
        name='prisonerlocation-delete-inactive'),
]
