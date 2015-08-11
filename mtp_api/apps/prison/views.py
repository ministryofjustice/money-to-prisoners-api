from rest_framework import mixins, viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import ActionsBasedPermissions

from .models import PrisonerLocation
from .serializers import PrisonerLocationSerializer


class PrisonerLocationView(
    mixins.CreateModelMixin, viewsets.GenericViewSet,
):
    queryset = PrisonerLocation.objects.all()

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions
    )
    serializer_class = PrisonerLocationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
