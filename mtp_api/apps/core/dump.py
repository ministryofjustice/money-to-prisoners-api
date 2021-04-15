import functools

from django.utils import timezone
from django.utils.module_loading import autodiscover_modules


class Serialiser:
    """
    Abstract base class for serialising data for exporting to Analytical Platform for example.
    Used to select modified records so that successive exports can update previously exported data.
    """
    _registry = {}
    record_type = NotImplemented

    def __init_subclass__(cls):
        if cls.record_type in cls._registry:
            raise KeyError('Serialiser already registered')
        cls._registry[cls.record_type] = cls

    def __init__(self):
        self.exported_at_local_time = timezone.now()

    @classmethod
    @functools.lru_cache()
    def get_serialisers(cls):
        autodiscover_modules('dump', register_to=cls)
        return cls._registry

    def get_queryset(self):
        raise NotImplementedError

    def get_modified_records(self, after, before):
        filters = {}
        if after:
            filters['modified__gte'] = after
        if before:
            filters['modified__lt'] = before
        return self.get_queryset().filter(**filters).order_by('pk').iterator(chunk_size=1000)

    def serialise(self, record):
        raise NotImplementedError
