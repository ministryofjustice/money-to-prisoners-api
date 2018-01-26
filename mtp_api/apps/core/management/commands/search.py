from django.core.management import BaseCommand, CommandError
from elasticsearch.helpers import bulk
from elasticsearch_dsl import Index

from core.search import registry


class Command(BaseCommand):
    """
    Control Elasticsearch index
    """
    help = __doc__.strip().splitlines()[0]

    def add_arguments(self, parser):
        actions = [attr[7:] for attr in filter(lambda attr: attr.startswith('handle_'), dir(self))]
        parser.add_argument('action', choices=actions)
        parser.add_argument('--no-input', action='store_false', dest='interactive', default=True)

    def handle(self, **options):
        return getattr(self, 'handle_%s' % options['action'])(**options)

    def handle_initialise(self, **options):
        verbosity = options['verbosity']
        for index_name, model_index in registry:
            if verbosity:
                self.stdout.write('Initialising search index `%s`' % index_name)
            model_index.init()

    def handle_index(self, **options):
        verbosity = options['verbosity']

        def generator():
            for index_name, model_index in registry:
                queryset = model_index.get_queryset()
                if verbosity:
                    self.stdout.write('Indexing `%s` with %d model instances' % (index_name, queryset.count()))
                for instance in queryset:
                    if verbosity > 1:
                        self.stdout.write('%r' % instance)
                    yield model_index.index_for_instance(instance, commit=False).to_dict(include_meta=True)

        success, errors = bulk(registry.client, actions=generator())
        for error in errors:
            self.stderr.write(error)

    def handle_clear(self, **options):
        interactive = options['interactive']
        if not interactive:
            raise CommandError('Interactive mode required')
        verbosity = options['verbosity']
        if input('Delete all indices? [y/N]: ').lower() != 'y':
            return
        for index_name, model_index in registry:
            if verbosity:
                self.stdout.write('Deleting index `%s`' % index_name)
            Index(index_name).delete()
