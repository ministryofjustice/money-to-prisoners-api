from prison.models import Prison
from rest_framework.viewsets import ModelViewSet
from rest_framework_extensions.mixins import NestedViewSetMixin

class PrisonViewSet(NestedViewSetMixin, ModelViewSet):
    model = Prison
