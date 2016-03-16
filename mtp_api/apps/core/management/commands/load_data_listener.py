import signal
import socketserver
import threading

from django.core.management import BaseCommand, call_command

from . import synchronised


class Command(BaseCommand):

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--port', dest='port',
                            type=int, default=8800,
                            help='Open listener socket at this port.')

    def handle(self, *fixture_labels, **options):
        listener_port = options.pop('port')
        self.start_listener(listener_port)

    def start_listener(self, listener_port):
        self.listener = socketserver.TCPServer(('0', listener_port), self.listener_request)
        self.listener.serve_forever()

    def listener_request(self, request, client_address, server):
        action = request.recv(1024).strip()
        if action == b'load_test_data':
            self.load_test_data(verbosity=1)
            request.sendall(b'done')
        elif action in (b'quit', b'exit', b'shutdown'):
            request.sendall(b'shutting down')
            threading.Timer(1, self.shutdown).start()
        else:
            request.sendall(b'unknown action')

    @synchronised
    def load_test_data(self, verbosity=1):
        call_command('load_test_data', protect_superusers=True, verbosity=verbosity)

    @synchronised
    def shutdown(self):
        self.stdout.write(self.style.WARNING('Shutting down'))
        if self.listener:
            self.listener.shutdown()
        if self.current_thread:
            signal.pthread_kill(self.current_thread.ident, signal.SIGINT)
