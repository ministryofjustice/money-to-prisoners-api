from functools import reduce

from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.db.models import Q
from django.db.transaction import atomic
from django.forms import ValidationError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets, mixins, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import FailedLoginAttempt, PrisonUserMapping
from .permissions import UserPermissions
from .serializers import UserSerializer, ChangePasswordSerializer


class UserViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin,
                  mixins.UpdateModelMixin, mixins.CreateModelMixin,
                  mixins.DestroyModelMixin, viewsets.GenericViewSet):
    lookup_field = 'username'

    queryset = User.objects.none()
    permission_classes = (IsAuthenticated, UserPermissions)
    serializer_class = UserSerializer

    def get_queryset(self):
        client_id = self.request.auth.application.client_id
        queryset = User.objects.filter(
            applicationusermapping__application__client_id=client_id,
            is_active=True
        )

        user_prisons = PrisonUserMapping.objects.get_prison_set_for_user(self.request.user)
        if len(user_prisons) > 0:
            prison_filters = []
            for prison in user_prisons:
                prison_filters.append(Q(prisonusermapping__prisons=prison))
            queryset = queryset.filter(
                reduce(lambda a, b: a | b, prison_filters)).distinct()
        return queryset

    def get_object(self, *args, **kwargs):
        """
        Make sure that you can only access your own user data,
        unless the user is a UserAdmin.
        """
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup = self.kwargs.get(lookup_url_kwarg, None)

        if (lookup == self.request.user.username or
                self.request.user.has_perm('auth.change_user')):
            return super(UserViewSet, self).get_object(*args, **kwargs)
        else:
            raise Http404()

    def perform_create(self, serializer):
        if 'user_admin' in self.request.data:
            serializer.save(user_admin=self.request.data['user_admin'])
        else:
            serializer.save()

    def perform_update(self, serializer):
        if 'user_admin' in self.request.data:
            serializer.save(user_admin=self.request.data['user_admin'])
        else:
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user != request.user:
            user.is_active = False
            user.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data={
                    '__all__': [_('You cannot delete yourself')]
                },
            )


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ChangePasswordSerializer

    @atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            try:
                if not FailedLoginAttempt.objects.is_locked_out(
                        request.user, request.auth.application):
                    if request.user.check_password(old_password):
                        FailedLoginAttempt.objects.delete_failed_attempts(
                            request.user, request.auth.application)
                        password_validation.validate_password(new_password, request.user)
                        request.user.set_password(new_password)
                        request.user.save()
                        return Response(status=204)
                    else:
                        FailedLoginAttempt.objects.add_failed_attempt(
                            request.user, request.auth.application)
                errors = {'old_password': [_('Your old password was entered incorrectly. '
                                             'Please enter it again.')]}
            except ValidationError as e:
                errors = {'new_password': e.error_list}
        else:
            errors = serializer.errors
        return Response(
            data={'errors': errors},
            status=400,
        )
