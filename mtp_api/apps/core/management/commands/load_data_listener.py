import socketserver
import threading

from django.conf import settings
from django.core.management import BaseCommand, call_command

from core.management.commands import synchronised


class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.listener = None
        self.verbosity = 1

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--port', dest='port',
                            type=int, default=8800,
                            help='Open listener socket at this port.')

    def handle(self, *args, **options):
        if settings.ENVIRONMENT == 'prod':
            self.stderr.write(self.style.WARNING('Disabled in prod environment'))
            return
        self.verbosity = options['verbosity']
        self.start_listener(options['port'])

    def start_listener(self, listener_port):
        self.stdout.write(self.style.SUCCESS('Listening on port %d' % listener_port))
        self.listener = socketserver.TCPServer(('0', listener_port), self.listener_request)
        self.listener.serve_forever()

    def listener_request(self, request, client_address, server):
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
    def load_test_data(self, verbosity=1, **kwargs):
        call_command(
            'load_test_data', no_protect_superusers=False,
            verbosity=verbosity, **kwargs
        )

    @synchronised
    def shutdown(self):
        self.stdout.write(self.style.WARNING('Shutting down'))
        if self.listener:
            self.listener.shutdown()
