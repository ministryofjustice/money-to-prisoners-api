from django.urls import include, re_path
from rest_framework_nested import routers

from security import views

router = routers.SimpleRouter()
router.register(r'senders', views.SenderProfileView)
sender_router = routers.NestedSimpleRouter(router, r'senders', lookup='sender')
sender_router.register(
    r'credits',
    views.SenderProfileCreditsView,
    basename='sender-credits',
)

router.register(r'recipients', views.RecipientProfileView)
recipient_router = routers.NestedSimpleRouter(router, r'recipients', lookup='recipient')
recipient_router.register(
    r'disbursements',
    views.RecipientProfileDisbursementsView,
    basename='recipient-disbursements',
)

router.register(r'prisoners', views.PrisonerProfileView)
prisoner_router = routers.NestedSimpleRouter(router, r'prisoners', lookup='prisoner')
prisoner_router.register(
    r'credits',
    views.PrisonerProfileCreditsView,
    basename='prisoner-credits',
)
prisoner_router.register(
    r'disbursements',
    views.PrisonerProfileDisbursementsView,
    basename='prisoner-disbursements',
)

router.register(r'searches', views.SavedSearchView)

router.register(r'security/checks/auto-accept', views.CheckAutoAcceptRuleView, basename='security-check-auto-accept')
router.register(r'security/checks', views.CheckView, basename='security-check')

router.register(
    r'security/monitored-email-addresses',
    views.MonitoredPartialEmailAddressView,
    basename='monitoredemailaddresses',
)


urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^', include(sender_router.urls)),
    re_path(r'^', include(recipient_router.urls)),
    re_path(r'^', include(prisoner_router.urls)),
    re_path(r'^monitored/$', views.MonitoredView.as_view(), name='monitored-list'),
]
