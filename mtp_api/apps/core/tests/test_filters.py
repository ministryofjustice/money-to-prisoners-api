from unittest import mock

from django_filters import FilterSet, STRICTNESS
from django_filters.constants import EMPTY_VALUES
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import SimpleTestCase
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.test import APIRequestFactory
from rest_framework.test import APITestCase

from core.filters import (
    LogNomsOpsSearchDjangoFilterBackend,
    MultipleValueFilter,
    PostcodeFilter,
    SplitTextInMultipleFieldsFilter,
)
from core.tests.utils import make_test_users
from mtp_auth.constants import (
    CASHBOOK_OAUTH_CLIENT_ID,
    NOMS_OPS_OAUTH_CLIENT_ID,
)
from mtp_auth.tests.utils import AuthTestCaseMixin
from user_event_log.models import UserEvent


User = get_user_model()


class SplitTextInMultipleFieldsFilterTestCase(SimpleTestCase):
    """
    Tests for SplitTextInMultipleFieldsFilter.
    """

    def test_no_field_names_raises_exception(self):
        """
        Test that an exception is raised if field_names is not passed in.
        """
        with self.assertRaises(ValueError):
            SplitTextInMultipleFieldsFilter()

    def test_filtering(self):
        """
        Test that the filtering logic generates the expected call to .filter().
        """
        qs = mock.Mock(spec=['filter'])
        f = SplitTextInMultipleFieldsFilter(
            field_names=('field1', 'field2'),
        )

        result = f.filter(qs, 'term1 term2')
        qs.filter.assert_called_once_with(
            Q(field1__exact='term1') | Q(field2__exact='term1'),
            Q(field1__exact='term2') | Q(field2__exact='term2'),
        )
        self.assertNotEqual(qs, result)

    def test_filtering_exclude(self):
        """
        Test that the filtering logic generates the expected call to .exclude()
        if the exclude=True argument is passed in.
        """
        qs = mock.Mock(spec=['exclude'])
        f = SplitTextInMultipleFieldsFilter(
            field_names=('field1', 'field2'),
            exclude=True,
        )

        result = f.filter(qs, 'term1 term2')
        qs.exclude.assert_called_once_with(
            Q(field1__exact='term1') | Q(field2__exact='term1'),
            Q(field1__exact='term2') | Q(field2__exact='term2'),
        )
        self.assertNotEqual(qs, result)

    def test_filtering_skipped_with_blank_value(self):
        """
        Test that no change to the qs is made if the value is empty.
        """
        for value in EMPTY_VALUES:
            qs = mock.Mock()
            f = SplitTextInMultipleFieldsFilter(
                field_names=('field1', 'field2'),
            )

            result = f.filter(qs, value)
            self.assertListEqual(qs.method_calls, [])
            self.assertEqual(qs, result)

    def test_filtering_lookup_expr(self):
        """
        Test that if a lookup_expr argument is passed in, its value is used to construct the qs.
        """
        qs = mock.Mock(spec=['filter'])
        f = SplitTextInMultipleFieldsFilter(
            field_names=('field1', 'field2'),
            lookup_expr='icontains',
        )

        result = f.filter(qs, 'term1 term2')
        qs.filter.assert_called_once_with(
            Q(field1__icontains='term1') | Q(field2__icontains='term1'),
            Q(field1__icontains='term2') | Q(field2__icontains='term2'),
        )
        self.assertNotEqual(qs, result)


class PostcodeFilterTestcase(SimpleTestCase):
    """
    Tests for the PostcodeFilter.
    """

    def test_overriding_lookup_expr_raises_exception(self):
        """
        Test that an exception is raised if lookup_expr is passed in.
        """
        with self.assertRaises(ValueError):
            PostcodeFilter(field_name='field', lookup_expr='iexact')

    def test_filtering(self):
        """
        Test that the filtering logic generates the expected call to .filter().
        """
        qs = mock.Mock(spec=['filter'])
        f = PostcodeFilter(field_name='field')

        result = f.filter(qs, 'sw1a 1aa')
        qs.filter.assert_called_once_with(
            field__iregex='s\\s*w\\s*1\\s*a\\s*1\\s*a\\s*a',
        )
        self.assertNotEqual(qs, result)

    def test_filtering_exclude(self):
        """
        Test that the filtering logic generates the expected call to .exclude()
        if the exclude=True argument is passed in.
        """
        qs = mock.Mock(spec=['exclude'])
        f = PostcodeFilter(field_name='field', exclude=True)

        result = f.filter(qs, 'sw1a 1aa')
        qs.exclude.assert_called_once_with(
            field__iregex='s\\s*w\\s*1\\s*a\\s*1\\s*a\\s*a',
        )
        self.assertNotEqual(qs, result)

    def test_filtering_skipped_with_blank_value(self):
        """
        Test that no change to the qs is made if the value is empty.
        """
        for value in EMPTY_VALUES:
            qs = mock.Mock()
            f = PostcodeFilter(field_name='field')

            result = f.filter(qs, value)
            self.assertListEqual(qs.method_calls, [])
            self.assertEqual(qs, result)


class UserTestFilter(FilterSet):
    """
    FilterSet for the User model to be used in tests.
    """
    pk = MultipleValueFilter(field_name='pk')

    class Meta:
        model = User
        fields = ('pk', 'first_name', 'last_name', 'last_login')
        strict = STRICTNESS.RETURN_NO_RESULTS


class UserTestView(
    mixins.ListModelMixin, mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    View for the User model to be used in the LogNomsOpsSearchDjangoFilterBackendTestCase tests
    """
    queryset = User.objects.all()
    filter_class = UserTestFilter
    filter_backends = (LogNomsOpsSearchDjangoFilterBackend, )
    permission_classes = (IsAuthenticated, )

    def get_serializer_class(self):
        return mock.Mock()


class LogNomsOpsSearchDjangoFilterBackendTestCase(AuthTestCaseMixin, APITestCase):
    """
    Tests for LogNomsOpsSearchDjangoFilterBackend.
    """
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
        # 200 as strict == STRICTNESS.RETURN_NO_RESULTS
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
