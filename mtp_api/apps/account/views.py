from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from core.permissions import ActionsBasedPermissions
from .models import File, FileType
from .serializers import FileSerializer, FileTypeSerializer


class FileTypeView(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = FileType.objects.all()
    serializer_class = FileTypeSerializer


class FileView(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = File.objects.all()
    serializer_class = FileSerializer

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions
    )
