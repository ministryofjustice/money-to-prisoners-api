from django.contrib.auth.models import User
from django.http import Http404

from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets, mixins

from .serializers import UserSerializer


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
