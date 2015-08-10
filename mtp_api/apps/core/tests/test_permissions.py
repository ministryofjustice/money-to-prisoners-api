import base64

from django.test import TestCase
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ImproperlyConfigured

from rest_framework import (
    HTTP_HEADER_ENCODING, authentication, serializers, generics,
    status, mixins, viewsets
)
from rest_framework.test import APIRequestFactory

from core.permissions import ActionsBasedPermissions


factory = APIRequestFactory()


class GroupSerializer(serializers.ModelSerializer):

    class Meta:
        model = Group
        fields = ('name',)


class TestViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet
):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    authentication_classes = [authentication.BasicAuthentication]
    permission_classes = [ActionsBasedPermissions]


def basic_auth_header(username, password):
    credentials = ('%s:%s' % (username, password))
    base64_credentials = base64.b64encode(credentials.encode(HTTP_HEADER_ENCODING)).decode(HTTP_HEADER_ENCODING)
    return 'Basic %s' % base64_credentials


class BaseActionsBasedPermissionsTests(TestCase):

    def setUp(self):
        User.objects.create_user('disallowed', 'disallowed@example.com', 'password')
        user = User.objects.create_user('permitted', 'permitted@example.com', 'password')
        user.user_permissions = [
            Permission.objects.get(codename='add_group'),
            Permission.objects.get(codename='change_group'),
            Permission.objects.get(codename='delete_group')
        ]

        self.permitted_credentials = basic_auth_header('permitted', 'password')
        self.disallowed_credentials = basic_auth_header('disallowed', 'password')

        self.group = Group.objects.create(name='foo')

        self.test_view = self._get_test_view()

    def _get_test_view(self):
        raise NotImplementedError()


class CreateActionsBasedPermissionsTests(BaseActionsBasedPermissionsTests):

    def _get_test_view(self):
        return TestViewSet.as_view({
            'post': 'create',
        })

    def test_has_create_permissions(self):
        request = factory.post(
            '/', {'name': 'foobar'}, format='json',
            HTTP_AUTHORIZATION=self.permitted_credentials
        )

        response = self.test_view(request)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_does_not_have_create_permissions(self):
        request = factory.post(
            '/', {'name': 'foobar'}, format='json',
            HTTP_AUTHORIZATION=self.disallowed_credentials
        )

        response = self.test_view(request)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ListActionsBasedPermissionsTests(BaseActionsBasedPermissionsTests):

    def _get_test_view(self):
        return TestViewSet.as_view({
            'get': 'list',
        })

    def test_list_does_not_have_default_permissions(self):
        request = factory.get(
            '/', format='json',
            HTTP_AUTHORIZATION=self.disallowed_credentials
        )

        response = self.test_view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RetrieveActionsBasedPermissionsTests(BaseActionsBasedPermissionsTests):

    def _get_test_view(self):
        return TestViewSet.as_view({
            'get': 'retrieve',
        })

    def test_retrieve_does_not_have_default_permissions(self):
        request = factory.get(
            '/', format='json',
            HTTP_AUTHORIZATION=self.disallowed_credentials
        )

        response = self.test_view(request, pk=self.group.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class UpdateActionsBasedPermissionsTests(BaseActionsBasedPermissionsTests):

    def _get_test_view(self):
        return TestViewSet.as_view({
            'put': 'update',
        })

    def test_has_update_permissions(self):
        request = factory.put(
            '/', {'name': 'foobar'}, format='json',
            HTTP_AUTHORIZATION=self.permitted_credentials
        )

        response = self.test_view(request, pk=self.group.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_does_not_have_update_permissions(self):
        request = factory.put(
            '/', {'name': 'foobar'}, format='json',
            HTTP_AUTHORIZATION=self.disallowed_credentials
        )

        response = self.test_view(request, pk=self.group.pk)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DestroyActionsBasedPermissionsTests(BaseActionsBasedPermissionsTests):

    def _get_test_view(self):
        return TestViewSet.as_view({
            'delete': 'destroy'
        })

    def test_has_destroy_permissions(self):
        request = factory.delete(
            '/', {'name': 'foobar'}, format='json',
            HTTP_AUTHORIZATION=self.permitted_credentials
        )

        response = self.test_view(request, pk=self.group.pk)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_does_not_have_destroy_permissions(self):
        request = factory.delete(
            '/', {'name': 'foobar'}, format='json',
            HTTP_AUTHORIZATION=self.disallowed_credentials
        )

        response = self.test_view(request, pk=self.group.pk)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ActionsBasedPermissionsOnViewSetsOnlyTests(BaseActionsBasedPermissionsTests):

    def _get_test_view(self):
        class TestView(
            mixins.CreateModelMixin,
            mixins.ListModelMixin,
            mixins.RetrieveModelMixin,
            mixins.UpdateModelMixin,
            mixins.DestroyModelMixin,
            generics.GenericAPIView
        ):
            queryset = Group.objects.all()
            serializer_class = GroupSerializer
            authentication_classes = [authentication.BasicAuthentication]
            permission_classes = [ActionsBasedPermissions]

        return TestView.as_view()

    def test_raises_exception_if_not_used_on_viewset(self):
        request = factory.get(
            '/', format='json',
            HTTP_AUTHORIZATION=self.permitted_credentials
        )

        self.assertRaises(
            ImproperlyConfigured, self.test_view, request
        )
