import logging

from django.core.management import BaseCommand
from django.db import DatabaseError, transaction

from core.models import ScheduledCommand

logger = logging.getLogger('mtp')


class Command(BaseCommand):
    def handle(self, *args, **options):
        commands = ScheduledCommand.objects.all()
        for command in commands:
            if command.is_scheduled():
                try:
                    with transaction.atomic():
                        locked_command = (
                            ScheduledCommand.objects.select_for_update(nowait=True)
                            .get(pk=command.pk)
                        )
                        if locked_command.is_scheduled():
                            locked_command.run()
                except DatabaseError:
                    logger.warning('Scheduled command "%s" failed to run due to database error', command)
                except Exception:
                    logger.exception('Scheduled command "%s" failed to run', command)
