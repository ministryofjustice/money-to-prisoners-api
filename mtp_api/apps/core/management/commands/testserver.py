import signal
import socketserver
import textwrap
import threading
import types

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.commands.testserver import Command as TestServerCommand
from django.db import connection

from core.management.commands import synchronised
from core.tests.utils import create_super_admin, give_superusers_full_access

User = get_user_model()


class Command(TestServerCommand):
    """
    Extension of the Django testserver command which creates extra testing data
    """
    help = textwrap.dedent(__doc__).strip()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_thread = None
        self.controller_thread = None
        self.controller = None

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--controller', dest='controller_port', type=int, default=8800,
                            help='Open controller socket at this port.')

    def handle(self, *fixture_labels, **options):
        this = self
        this.verbosity = options.get('verbosity')
        controller_port = options.pop('controller_port')

        required_fixture_labels = ['initial_groups', 'initial_types', 'test_prisons']
        specified_fixture_labels = fixture_labels
        fixture_labels = required_fixture_labels + list(
            set(specified_fixture_labels) - set(required_fixture_labels)
        )

        create_test_db = connection.creation.create_test_db

        def extended_create_test_db(self, *args, **kwargs):
            # extends the test db creation method to load and generate testing data
            db_name = create_test_db(*args, **kwargs)
            call_command('loaddata', *fixture_labels, **{'verbosity': this.verbosity})
            this.load_test_data()
            this._create_super_admin()
            return db_name

        connection.creation.create_test_db = types.MethodType(
            extended_create_test_db,
            connection.creation
        )

        if controller_port:
            self.current_thread = threading.current_thread()
            self.controller_thread = threading.Thread(
                target=self.start_controller,
                args=(controller_port,),
                daemon=True,
            )
            self.controller_thread.start()

        super().handle(*fixture_labels, **options)

    @synchronised
    def load_test_data(self, verbosity=1, **kwargs):
        call_command(
            'load_test_data', no_protect_superusers=False,
            verbosity=verbosity, **kwargs
        )

    @synchronised
    def _create_super_admin(self):
        create_super_admin(self.stdout, self.style.SUCCESS)
        give_superusers_full_access()

    def start_controller(self, controller_port):
        self.controller = socketserver.TCPServer(('0', controller_port), self.controller_request)
        self.controller.serve_forever()

    def controller_request(self, request, client_address, server):
        action = request.recv(1024).strip()
        if self.verbosity > 1:
            self.stdout.write('Message received: %s' % action)
        if action == b'load_test_data':
            self.load_test_data(verbosity=1)
            request.sendall(b'done')
        elif action == b'load_nomis_test_data':
            self.load_test_data(
                verbosity=1, prisons=['nomis-api-dev'],
                prisoners=['nomis-api-dev'], credits='nomis'
            )
            request.sendall(b'done')
        elif action in (b'quit', b'exit', b'shutdown'):
            request.sendall(b'shutting down')
            threading.Timer(1, self.shutdown).start()
        else:
            request.sendall(b'unknown action')

    @synchronised
    def shutdown(self):
        self.stdout.write(self.style.WARNING('Shutting down'))
        if self.controller:
            self.controller.shutdown()
        if self.current_thread:
            signal.pthread_kill(self.current_thread.ident, signal.SIGINT)
