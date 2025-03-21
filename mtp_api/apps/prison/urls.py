from django.urls import include, re_path
from rest_framework import routers

from prison import views

router = routers.DefaultRouter()
router.register(r'prisoner_locations', views.PrisonerLocationView, basename='prisonerlocation')
router.register(r'prisoner_validity', views.PrisonerValidityView, basename='prisoner_validity')
router.register(r'prisoner_account_balances', views.PrisonerAccountBalanceView, basename='prisoner_account_balance')
router.register(r'prisons', views.PrisonView, basename='prison')
router.register(r'prison_populations', views.PopulationView, basename='prison_population')
router.register(r'prison_categories', views.CategoryView, basename='prison_category')
router.register(
    r'prisoner_credit_notice_email', views.PrisonerCreditNoticeEmailView, basename='prisoner_credit_notice_email'
)

urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(
        r'^prisoner_locations/actions/delete_old/$',
        views.DeleteOldPrisonerLocationsView.as_view(),
        name='prisonerlocation-delete-old',
    ),
    re_path(
        r'^prisoner_locations/actions/delete_inactive/$',
        views.DeleteInactivePrisonerLocationsView.as_view(),
        name='prisonerlocation-delete-inactive',
    ),
]
