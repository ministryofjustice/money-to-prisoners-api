from django.core.management import BaseCommand

from core.models import ScheduledCommand


class Command(BaseCommand):

    def handle(self, *args, **options):
        commands = ScheduledCommand.objects.select_for_update().all()
        for command in commands:
            if command.is_scheduled():
                command.run()
