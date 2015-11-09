from rest_framework import mixins, viewsets, filters
from rest_framework.permissions import IsAuthenticated

from core.permissions import ActionsBasedPermissions
from .models import Batch
from .serializers import BatchSerializer


class BatchView(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Batch.objects.all().order_by('-created')
    serializer_class = BatchSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filter_fields = ('label',)

    permission_classes = (
        IsAuthenticated, ActionsBasedPermissions
    )
