import os

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.module_loading import autodiscover_modules
from elasticsearch import Elasticsearch, RequestsHttpConnection
from elasticsearch_dsl import DocType
from elasticsearch_dsl.connections import connections as elasticsearch_connections
from requests_aws4auth import AWS4Auth


class ModelIndex(DocType):
    model = NotImplemented

    @classmethod
    def get_queryset(cls):
        return cls.model.objects.all()

    @classmethod
    def serialise(cls, instance):
        # model_fields = set(field.name for field in cls.model._meta.fields)
        # index_fields = set(cls._doc_type.mapping)
        # common_fields = model_fields & index_fields
        # other_index_fields = index_fields - common_fields
        data = {}
        for field in cls._doc_type.mapping:
            if hasattr(instance, field):
                data[field] = getattr(instance, field)
        return data

    @classmethod
    def index_for_instance(cls, instance, commit=True):
        data = cls.serialise(instance)
        index = cls(meta={'id': instance.pk}, **data)
        if commit:
            index.save()
        return index


class Registry:
    def __init__(self):
        self._registry = {}

    def __iter__(self):
        for index_name, model_index in self._registry.items():
            yield index_name, model_index

    @property
    def client(self) -> Elasticsearch:
        return elasticsearch_connections.get_connection()

    def setup(self):
        access_key = os.environ.get('AWS_ACCESS_KEY_ID')
        secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
        region = os.environ.get('AWS_DEFAULT_REGION') or 'eu-west-1'

        if not access_key or not secret_key:
            import boto3

            credentials = boto3.Session().get_credentials()
            access_key = credentials.access_key
            secret_key = credentials.secret_key

        kwargs = dict(
            hosts=[{'host': settings.ELASTICSEARCH_DOMAIN, 'port': 443}],
            http_auth=AWS4Auth(access_key, secret_key, region, 'es'),
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        )

        elasticsearch_connections.create_connection(**kwargs)

        if not self._registry:
            autodiscover_modules('search_index', register_to=self)

    def register(self, model_index):
        @receiver(post_save, sender=model_index.model)
        def instance_saved(instance, **_):
            model_index.index_for_instance(instance)

        model_index._post_save = instance_saved
        self._registry[model_index._doc_type.index] = model_index
        return model_index


registry = Registry()
