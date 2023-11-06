from unittest import mock

from django_filters import FilterSet
from django.contrib.auth import get_user_model
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIRequestFactory
from rest_framework.test import APITestCase

from core.filters import (LogNomsOpsSearchDjangoFilterBackend, MultipleValueFilter)
from core.tests.utils import make_test_users
from mtp_auth.constants import (
    CASHBOOK_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID,
)
from mtp_auth.tests.utils import AuthTestCaseMixin
from user_event_log.models import UserEvent


User = get_user_model()


class UserTestFilter(FilterSet):
    """
    FilterSet for the User model to be used in tests.
    """
    pk = MultipleValueFilter(field_name='pk')

    class Meta:
        model = User
        fields = ('pk', 'first_name', 'last_name', 'last_login')


class UserTestView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    View for the User model to be used in the LogNomsOpsSearchDjangoFilterBackendTestCase tests
    """
    queryset = User.objects.all()
    filterset_class = UserTestFilter
    filter_backends = (LogNomsOpsSearchDjangoFilterBackend, )
    permission_classes = (IsAuthenticated, )

    def get_serializer_class(self):
        return mock.Mock()


class LogNomsOpsSearchDjangoFilterBackendTestCase(AuthTestCaseMixin, APITestCase):
    # NB: LogNomsOpsSearchDjangoFilterBackend is not in use

    fixtures = ['initial_types.json', 'test_prisons.json', 'initial_groups.json']

    def setUp(self):
        super().setUp()
        test_users = make_test_users()
        self.security_staff = test_users['security_staff'][0]

    def test_logs(self):
        """
        Test that calling the list endpoint using the NOMS OPS Client with some filters
        creates a UserEvent record.
        """
        factory = APIRequestFactory()
        request = factory.get(
            '/',
            data={
                'first_name': 'My first name',
                'last_name': 'My last name',
            },
            content_type='application/json',
            Authorization=self.get_http_authorization_for_user(
                self.security_staff,
                client_id=NOMS_OPS_OAUTH_CLIENT_ID,
            )
        )

        view = UserTestView.as_view({'get': 'list'})
        response = view(request)
        self.assertEqual(response.status_code, 200)

        user_events = UserEvent.objects.all()
        self.assertEqual(user_events.count(), 1)

        user_event = user_events.first()
        self.assertDictEqual(
            user_event.data,
            {
                'filters': {
                    'last_name': 'My last name',
                    'first_name': 'My first name',
                },
                'results': 0,
            }
        )

    def test_doesnt_log_if_not_noms_ops(self):
        """
        Test that calling the list endpoint without using the NOMS OPS Client doesn't create
        any UserEvent record.
        """
        factory = APIRequestFactory()
        request = factory.get(
            '/',
            data={
                'first_name': 'My first name',
                'last_name': 'My last name',
            },
            content_type='application/json',
            Authorization=self.get_http_authorization_for_user(
                self.security_staff,
                client_id=CASHBOOK_OAUTH_CLIENT_ID,
            )
        )

        view = UserTestView.as_view({'get': 'list'})
        response = view(request)
        self.assertEqual(response.status_code, 200)

        user_events = UserEvent.objects.all()
        self.assertEqual(user_events.count(), 0)

    def test_doesnt_log_if_no_filters_is_used(self):
        """
        Test that calling the list endpoint without filters doesn't create any UserEvent record.
        """
        factory = APIRequestFactory()
        request = factory.get(
            '/',
            data={},
            content_type='application/json',
            Authorization=self.get_http_authorization_for_user(
                self.security_staff,
                client_id=NOMS_OPS_OAUTH_CLIENT_ID,
            )
        )

        view = UserTestView.as_view({'get': 'list'})
        response = view(request)
        self.assertEqual(response.status_code, 200)

        user_events = UserEvent.objects.all()
        self.assertEqual(user_events.count(), 0)

    def test_doesnt_log_if_pk_filter_is_used(self):
        """
        Test that calling the list endpoint with a `pk` filter doesn't create any UserEvent record.
        This is because the credits GET object endpoint is currently implemented as list with a pk filter.
        """
        factory = APIRequestFactory()
        request = factory.get(
            '/',
            data={
                'pk': 1,
            },
            content_type='application/json',
            Authorization=self.get_http_authorization_for_user(
                self.security_staff,
                client_id=NOMS_OPS_OAUTH_CLIENT_ID,
            )
        )

        view = UserTestView.as_view({'get': 'list'})
        response = view(request)
        self.assertEqual(response.status_code, 200)

        user_events = UserEvent.objects.all()
        self.assertEqual(user_events.count(), 0)

    def test_doesnt_log_if_filters_in_error(self):
        """
        Test that if the filters used are in error, no UserEvent record is created.
        """
        factory = APIRequestFactory()
        request = factory.get(
            '/',
            data={
                'last_login': 'invalid',
            },
            content_type='application/json',
            Authorization=self.get_http_authorization_for_user(
                self.security_staff,
                client_id=NOMS_OPS_OAUTH_CLIENT_ID,
            )
        )

        view = UserTestView.as_view({'get': 'list'})
        response = view(request)
        # 200 as strict == STRICTNESS.RETURN_NO_RESULTS is now hardcoded since django-filters 2.0
        self.assertEqual(response.status_code, 200)

        user_events = UserEvent.objects.all()
        self.assertEqual(user_events.count(), 0)

    def test_doesnt_log_if_not_list(self):
        """
        Test that calling any other non-list-endpoint doesn't create any UserEvent record.
        """
        factory = APIRequestFactory()
        request = factory.get(
            f'/{self.security_staff.pk}/',
            data={},
            content_type='application/json',
            Authorization=self.get_http_authorization_for_user(
                self.security_staff,
                client_id=NOMS_OPS_OAUTH_CLIENT_ID,
            )
        )

        view = UserTestView.as_view({'get': 'retrieve'})
        response = view(request, pk=self.security_staff.pk)
        self.assertEqual(response.status_code, 200)

        user_events = UserEvent.objects.all()
        self.assertEqual(user_events.count(), 0)
