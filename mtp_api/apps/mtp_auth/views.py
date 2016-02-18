from django.contrib.auth.models import User
from django.db.transaction import atomic
from django.http import Http404
from django.utils.translation import ugettext_lazy as _
from rest_framework import viewsets, mixins, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import FailedLoginAttempt
from .serializers import UserSerializer, ChangePasswordSerializer


class UserViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    lookup_field = 'username'

    queryset = User.objects.all()
    permission_classes = (IsAuthenticated,)
    serializer_class = UserSerializer

    def get_object(self, *args, **kwargs):
        """
        Make sure that you can only access your own user data.
        """
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup = self.kwargs.get(lookup_url_kwarg, None)

        if lookup != self.request.user.username:
            raise Http404()

        return super(UserViewSet, self).get_object(*args, **kwargs)


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ChangePasswordSerializer

    @atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            if not FailedLoginAttempt.objects.is_locked_out(
                    request.user, request.auth.application):
                if request.user.check_password(old_password):
                    FailedLoginAttempt.objects.delete_failed_attempts(
                        request.user, request.auth.application)
                    request.user.set_password(new_password)
                    request.user.save()
                    return Response(status=204)
                else:
                    FailedLoginAttempt.objects.add_failed_attempt(
                        request.user, request.auth.application)
            return Response(
                data={'errors': _('Old password was incorrect.')},
                status=400
            )
        else:
            return Response(
                data=serializer.errors,
                status=400,
            )
